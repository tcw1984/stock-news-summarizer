# Install necessary packages if needed
import subprocess
subprocess.run(['pip', 'install', 'groq', 'gradio', 'beautifulsoup4', 'yfinance', 'streamlit', 'python-dotenv'])

import os
import requests
from groq import Groq, APIError
from bs4 import BeautifulSoup
import streamlit as st
from datetime import datetime, timedelta
import yfinance as yf
import pandas as pd
import time
import random
import re
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Fetch the Groq API Key from environment variables
API_KEY = os.getenv("GROQ_API_KEY")
if not API_KEY:
    raise ValueError("GROQ_API_KEY not found. Please add it to the .env file.")

# Initialize Groq client
client = Groq(api_key=API_KEY)

# Function to fetch news articles
def fetch_news(company_name, ticker, start_date, end_date, seen_articles=None):
    if seen_articles is None:
        seen_articles = set()

    articles = []
    query = f'"{company_name}" OR {ticker} stock'

    # Google News RSS feed URL
    base_url = 'https://news.google.com/rss/search'

    params = {
        'q': query,
        'hl': 'en-US',
        'gl': 'US',
        'ceid': 'US:en',
    }

    response = requests.get(base_url, params=params)
    soup = BeautifulSoup(response.content, 'xml')

    items = soup.find_all('item')

    for item in items:
        try:
            title = item.title.text
            link = item.link.text
            pub_date_str = item.pubDate.text
            pub_date = datetime.strptime(pub_date_str, '%a, %d %b %Y %H:%M:%S %Z').date()

            if start_date <= pub_date <= end_date:
                article_key = (title, link)
                if article_key not in seen_articles:
                    articles.append((pub_date, title, link))
                    seen_articles.add(article_key)
        except Exception as e:
            print(f"Error processing article: {e}")

    return articles

# Function to summarize articles
def summarize_articles(articles):
    max_model_tokens = 8192
    max_output_tokens = 512
    max_tokens_per_minute = 7000
    estimated_tokens_per_char = 1 / 4

    summaries = []
    batch_articles = articles.copy()
    while batch_articles:
        num_articles = len(batch_articles)
        while num_articles > 0:
            batch = batch_articles[:num_articles]
            summary_input = "\n".join([f"{title[:80]} (Link: {link})" for _, title, link in batch])
            input_tokens = int(len(summary_input) * estimated_tokens_per_char)
            total_tokens = input_tokens + max_output_tokens

            if total_tokens <= min(max_model_tokens, max_tokens_per_minute):
                try:
                    completion = client.chat.completions.create(
                        model="llama-3.2-90b-text-preview",
                        messages=[{'role': 'user', 'content': f"Summarize key updates or issues of the company based on the following articles:\n{summary_input}"}],
                        temperature=1,
                        max_tokens=max_output_tokens,
                        top_p=1,
                        stream=False,
                        stop=None,
                    )
                    summary = completion.choices[0].message.content.strip()
                    summaries.append(summary)
                    batch_articles = batch_articles[num_articles:]
                    break
                except APIError as e:
                    error_message = str(e)
                    if 'rate_limit_exceeded' in error_message:
                        wait_time_match = re.search(r'Please try again in ([\d.]+)s', error_message)
                        wait_time = float(wait_time_match.group(1)) + 1 if wait_time_match else 60
                        print(f"Rate limit exceeded. Waiting for {wait_time} seconds before retrying...")
                        time.sleep(wait_time)
                    elif 'context_length_exceeded' in error_message or 'Please reduce the length of the messages or completion' in error_message:
                        print("Context length exceeded. Reducing batch size...")
                        num_articles -= 1
                    else:
                        print(f"Error generating summary: {error_message}")
                        return "\n\n".join(summaries)
            else:
                num_articles -= 1

        if num_articles == 0:
            print("Unable to process articles due to size limitations.")
            break

    final_summary = "\n\n".join(summaries)
    return final_summary

# Function to summarize stock news
def summarize_stock_news(ticker, start_date, end_date):
    if not start_date:
        start_date = (datetime.now() - timedelta(days=30)).date()
    if not end_date:
        end_date = datetime.now().date()

    try:
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date.strip(), '%Y-%m-%d').date()
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date.strip(), '%Y-%m-%d').date()
    except ValueError:
        return "Please enter valid dates in YYYY-MM-DD format."

    if start_date > end_date:
        return "Start date must be before end date."

    try:
        stock = yf.Ticker(ticker)
        company_name = stock.info.get('longName', '')
        if not company_name:
            return "Invalid stock ticker."
    except Exception:
        return "Failed to retrieve company information."

    articles = fetch_news(company_name, ticker, start_date, end_date)

    if not articles:
        return "No articles found."

    summary = summarize_articles(articles)

    return summary

# Streamlit UI setup
st.title("Stock News Summarizer")

# Load environment variables from .env file
load_dotenv()

# Correct password stored in .env file for security (you can also hard-code it, but it's less secure)
correct_password = os.getenv("APP_PASSWORD")

# Create a password input field
password = st.text_input("Enter Password", type="password")

# Check if the password is correct
if password == correct_password:
    st.success("Password correct! You can now use the app.")
    
    # Input fields for stock ticker, start date, and end date
    ticker = st.text_input("Stock Ticker", "NVDA")
    start_date = st.date_input("Start Date", datetime.now() - timedelta(days=30))
    end_date = st.date_input("End Date", datetime.now())

    # Summarize button
    if st.button("Summarize"):
        summary = summarize_stock_news(ticker, start_date, end_date)
        
        # Display the summary
        st.write(summary)

        # Add the Copy button with JavaScript to copy the text to the clipboard
        copy_button = f"""
        <button onclick="copyToClipboard()">
            Copy to Clipboard
        </button>
        <script>
            function copyToClipboard() {{
                if (navigator.clipboard) {{
                    navigator.clipboard.writeText(`{summary}`).then(function() {{
                        alert('Copied to clipboard!');
                    }}, function(err) {{
                        alert('Could not copy text: ', err);
                    }});
                }} else {{
                    // Fallback for older browsers
                    var textArea = document.createElement("textarea");
                    textArea.value = `{summary}`;
                    document.body.appendChild(textArea);
                    textArea.select();
                    try {{
                        document.execCommand('copy');
                        alert('Copied to clipboard!');
                    }} catch (err) {{
                        alert('Could not copy text: ', err);
                    }}
                    document.body.removeChild(textArea);
                }}
            }}
        </script>
        """
        st.components.v1.html(copy_button)
else:
    st.warning("Please enter the correct password to proceed.")