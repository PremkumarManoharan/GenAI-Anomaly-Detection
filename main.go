package main

import (
	"bytes"
	"encoding/json"
	"io"
	"log"
	"net/http"
	"os"
)

type PromptRequest struct {
	Prompt string `json:"prompt"`
}

type FastAPIPromptRequest struct {
	Text string `json:"text"`
}

type Response struct {
	GeneratedText string `json:"generated_text"`
	Anomaly       string `json:"anomaly,omitempty"`
	Warning       string `json:"warning,omitempty"`
	SensitiveData []struct {
		Entity string `json:"entity"`
		Value  string `json:"value"`
	} `json:"sensitive_data,omitempty"`
}

func main() {
	http.HandleFunc("/detect", corsHandler(detectHandler))
	log.Fatal(http.ListenAndServe(":8080", nil))
}

func detectHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodOptions {
		corsHandler(func(w http.ResponseWriter, r *http.Request) {})(w, r)
		return
	}

	fastAPIURL := os.Getenv("FASTAPI_URL")
	if fastAPIURL == "" {
		http.Error(w, "FASTAPI_URL environment variable not set", http.StatusInternalServerError)
		return
	}

	var promptReq PromptRequest
	err := json.NewDecoder(r.Body).Decode(&promptReq)
	if err != nil {
		http.Error(w, "Invalid request payload", http.StatusBadRequest)
		return
	}

	fastAPIPromptReq := FastAPIPromptRequest{Text: promptReq.Prompt}
	jsonData, err := json.Marshal(fastAPIPromptReq)
	if err != nil {
		http.Error(w, "Failed to marshal request payload", http.StatusInternalServerError)
		return
	}

	resp, err := http.Post(fastAPIURL+"/detect_anomalies/", "application/json", bytes.NewBuffer(jsonData))
	if err != nil {
		log.Printf("Error making request to FastAPI service: %s", err)
		http.Error(w, "Failed to communicate with detection service", http.StatusInternalServerError)
		return
	}
	defer resp.Body.Close()

	responseData, err := io.ReadAll(io.Reader(resp.Body))
	if err != nil {
		http.Error(w, "Failed to read response from detection service", http.StatusInternalServerError)
		return
	}

	var response Response
	err = json.Unmarshal(responseData, &response)
	if err != nil {
		http.Error(w, "Failed to parse response from detection service", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(response)
}

func corsHandler(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type")
		if r.Method == http.MethodOptions {
			return
		}
		next(w, r)
	}
}
