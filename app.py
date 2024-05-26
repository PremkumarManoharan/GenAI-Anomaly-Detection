from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from openai import OpenAI
import os
from dotenv import load_dotenv
import psycopg2
from transformers import TFAutoModelForTokenClassification, AutoTokenizer, pipeline

load_dotenv()
# Load the pre-trained NER model from Hugging Face once
model_name = "dbmdz/bert-large-cased-finetuned-conll03-english"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = TFAutoModelForTokenClassification.from_pretrained(model_name)
ner_pipeline = pipeline("ner", model=model, tokenizer=tokenizer)

# Set up PostgreSQL connection
conn = psycopg2.connect(
    dbname=os.getenv("POSTGRES_DB"),
    user=os.getenv("POSTGRES_USER"),
    password=os.getenv("POSTGRES_PASSWORD"),
    host=os.getenv("POSTGRES_HOST"),
)

cursor = conn.cursor()

app = FastAPI()


class Prompt(BaseModel):
    text: str


# Function to detect sensitive data using the NER model
def detect_sensitive_data(text):
    entities = ner_pipeline(text)
    sensitive_entities = [
        entity
        for entity in entities
        if entity["entity"] in ["B-PER", "I-PER", "B-LOC", "I-LOC", "B-ORG", "I-ORG"]
    ]
    return sensitive_entities


# Function to generate text using GPT-3.5-turbo
def generate_text(prompt):
    # Set up the OpenAI API key
    client = OpenAI(
        api_key=os.environ.get("OPENAI_API_KEY"),
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
    return chat_completion.choices[0].message.content.strip()


@app.post("/detect_anomalies/")
async def detect_anomalies(prompt: Prompt):
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

        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.on_event("shutdown")
def shutdown_event():
    cursor.close()
    conn.close()
