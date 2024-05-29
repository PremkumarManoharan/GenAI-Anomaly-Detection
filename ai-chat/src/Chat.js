import React, { useState } from 'react';
import axios from 'axios';
import './Chat.css';

const Chat = () => {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (input.trim() === '') return;

    const userMessage = { sender: 'user', text: input };
    setMessages((prevMessages) => [...prevMessages, userMessage]);

    try {
      const response = await axios.post(`${process.env.REACT_APP_BACKEND_URL}/detect`, { prompt: input });
      let aiMessage;
      if (response.data.warning) {
        aiMessage = { sender: 'ai', text: `Warning: ${response.data.warning}` };
      } else {
        aiMessage = { sender: 'ai', text: response.data.generated_text };
      }
      setMessages((prevMessages) => [...prevMessages, aiMessage]);
    } catch (error) {
      console.error('Error:', error);
      const errorMessage = { sender: 'ai', text: 'Sorry, something went wrong.' };
      setMessages((prevMessages) => [...prevMessages, errorMessage]);
    }

    setInput('');
  };

  return (
    <div className="chat-container">
      <div className="chat-box">
        {messages.map((message, index) => (
          <div key={index} className={`chat-message ${message.sender}`}>
            {message.text}
          </div>
        ))}
      </div>
      <form onSubmit={handleSubmit} className="chat-input-form">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Type a message..."
          className="chat-input"
        />
        <button type="submit" className="chat-submit-button">Send</button>
      </form>
    </div>
  );
};

export default Chat;
