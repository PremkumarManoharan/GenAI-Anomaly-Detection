package main

import (
	"bytes"
	"encoding/json"
	"io/ioutil"
	"log"
	"net/http"
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
	http.HandleFunc("/detect", detectHandler)
	http.Handle("/", http.FileServer(http.Dir("./static")))
	log.Fatal(http.ListenAndServe(":8080", nil))
}

func detectHandler(w http.ResponseWriter, r *http.Request) {
	// Parse the request body to get the prompt
	var promptReq PromptRequest
	err := json.NewDecoder(r.Body).Decode(&promptReq)
	if err != nil {
		http.Error(w, "Invalid request payload", http.StatusBadRequest)
		return
	}

	// Convert the prompt request to FastAPI request format
	fastAPIPromptReq := FastAPIPromptRequest{Text: promptReq.Prompt}
	jsonData, err := json.Marshal(fastAPIPromptReq)
	if err != nil {
		http.Error(w, "Failed to marshal request payload", http.StatusInternalServerError)
		return
	}

	// Make a POST request to the FastAPI service
	log.Println(bytes.NewBuffer(jsonData))
	resp, err := http.Post("http://localhost:8000/detect_anomalies/", "application/json", bytes.NewBuffer(jsonData))
	if err != nil {
		log.Printf("Error making request to FastAPI service: %s", err)
		http.Error(w, "Failed to communicate with detection service", http.StatusInternalServerError)
		return
	}
	defer resp.Body.Close()

	// Read the response from the FastAPI service
	responseData, err := ioutil.ReadAll(resp.Body)
	if err != nil {
		http.Error(w, "Failed to read response from detection service", http.StatusInternalServerError)
		return
	}

	// Parse the response from the FastAPI service
	var response Response
	err = json.Unmarshal(responseData, &response)
	if err != nil {
		http.Error(w, "Failed to parse response from detection service", http.StatusInternalServerError)
		return
	}

	// Return the results
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(response)
}
