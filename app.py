from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from openai import OpenAI
import os
from dotenv import load_dotenv
import psycopg2
from psycopg2 import sql
from transformers import TFAutoModelForTokenClassification, AutoTokenizer, pipeline

load_dotenv()

# Load the pre-trained NER model from Hugging Face once
model_name = "dbmdz/bert-large-cased-finetuned-conll03-english"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = TFAutoModelForTokenClassification.from_pretrained(model_name)
ner_pipeline = pipeline("ner", model=model, tokenizer=tokenizer)

print("Models loaded")

# Set up PostgreSQL connection
conn = psycopg2.connect(
    dbname=os.getenv("POSTGRES_DB", "postgres"),
    user=os.getenv("POSTGRES_USER"),
    password=os.getenv("POSTGRES_PASSWORD"),
    host=os.getenv("POSTGRES_HOST"),
)

conn.autocommit = True
cursor = conn.cursor()

# Create database if it does not exist
db_name = os.getenv("POSTGRES_DB")
cursor.execute(sql.SQL("SELECT 1 FROM pg_database WHERE datname = %s"), [db_name])
exists = cursor.fetchone()
if not exists:
    cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))
    print(f"Database {db_name} created")

# Reconnect to the newly created database
conn.close()
conn = psycopg2.connect(
    dbname=db_name,
    user=os.getenv("POSTGRES_USER"),
    password=os.getenv("POSTGRES_PASSWORD"),
    host=os.getenv("POSTGRES_HOST"),
)
conn.autocommit = True
cursor = conn.cursor()

# Create table if it does not exist
create_table_query = """
CREATE TABLE IF NOT EXISTS anomalies (
    id SERIAL PRIMARY KEY,
    prompt TEXT NOT NULL,
    generated_text TEXT NOT NULL,
    anomaly TEXT,
    warning TEXT,
    sensitive_data JSONB,
    anomaly_source TEXT,
    time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""
cursor.execute(create_table_query)
print("Table anomalies checked/created")

app = FastAPI()


class Prompt(BaseModel):
    text: str


# Function to detect sensitive data using the NER model
def detect_sensitive_data(text):
    entities = ner_pipeline(text)
    print(entities)
    sensitive_entities = [
        entity
        for entity in entities
        if entity["entity"] in ["B-PER", "I-PER", "B-LOC", "I-LOC", "B-ORG", "I-ORG"]
    ]
    print(sensitive_entities)
    return sensitive_entities


# Function to generate text using GPT-3.5-turbo
def generate_text(prompt):
    # Set up the OpenAI API key
    client = OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
    )

    chat_completion = client.chat.completions.create(
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
        model="gpt-3.5-turbo",
    )
    print(chat_completion.choices[0].message.content.strip())
    return chat_completion.choices[0].message.content.strip()


@app.post("/detect_anomalies/")
async def detect_anomalies(prompt: Prompt):
    print(prompt.text)
    try:
        sensitive_entities = detect_sensitive_data(prompt.text)
        response = {}
        if sensitive_entities:
            warning_message = "Sensitive data detected in user input. Please remove sensitive information and try again."
            response = {
                "generated_text": "Data was not provided to AI",
                "anomaly": (
                    sensitive_entities[0]["entity"] if sensitive_entities else None
                ),
                "warning": warning_message,
                "sensitive_data": [
                    {"entity": entity["entity"], "value": entity["word"]}
                    for entity in sensitive_entities
                ],
            }
            # Insert sensitive prompt into the PostgreSQL database
            cursor.execute(
                "INSERT INTO anomalies (prompt, generated_text, anomaly, anomaly_source, time) VALUES (%s, %s, %s, %s, NOW())",
                (
                    prompt.text,
                    "Data was not provided to AI",
                    sensitive_entities[0]["entity"] if sensitive_entities else None,
                    "input",
                ),
            )
            conn.commit()
        else:
            print(prompt.text)
            generated_text = generate_text(prompt.text)
            anomalies = detect_sensitive_data(generated_text)
            response = {
                "generated_text": generated_text,
                "anomaly": None,
                "warning": None,
                "sensitive_data": [],
            }

            if anomalies:
                warning_message = "Sensitive data detected in AI generated Output. Please do not ask for sensitive information and try again."
                response["sensitive_data"] = [
                    {"entity": entity["entity"], "value": entity["word"]}
                    for entity in anomalies
                ]
                response["anomaly"] = anomalies[0]["entity"]
                response["warning"] = warning_message
                # Insert anomalies into the PostgreSQL database if any
                cursor.execute(
                    "INSERT INTO anomalies (prompt, generated_text, anomaly, anomaly_source, time) VALUES (%s, %s, %s, %s, NOW())",
                    (
                        prompt.text,
                        generated_text,
                        anomalies[0]["entity"] if anomalies else None,
                        "output",
                    ),
                )
                conn.commit()
        print(response)

        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.on_event("shutdown")
def shutdown_event():
    cursor.close()
    conn.close()
