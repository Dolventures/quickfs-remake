# Financials Explorer

A local web app that pulls historical financial data directly from SEC EDGAR filings and displays it in a clean, interactive dashboard. Look up any U.S. publicly traded company by ticker symbol and see:

- Income statement, balance sheet, and cash flow history
- Key valuation metrics (EV/EBITDA, EV/Sales, FCF yield)
- Returns history (ROIC, ROE, ROA)
- Growth CAGRs
- How current valuation compares to historical median

All financial data comes from official SEC filings — no paid subscription required.

---

## What You Need Before Starting

- A computer running **Mac, Windows, or Linux**
- An internet connection
- About 10 minutes

---

## Step 1 — Install Python

Python is the programming language this app runs on.

1. Go to **https://www.python.org/downloads/**
2. Click the big yellow **Download Python** button
3. Run the installer
   - On **Windows**: check the box that says **"Add Python to PATH"** before clicking Install — this is important
   - On **Mac**: follow the prompts, defaults are fine
4. When it finishes, open a terminal:
   - **Mac**: press `Command + Space`, type `Terminal`, press Enter
   - **Windows**: press the Windows key, type `cmd`, press Enter

Verify Python installed correctly by typing this and pressing Enter:
```
python --version
```
You should see something like `Python 3.12.0`. If you see an error, try `python3 --version` instead — and use `python3` anywhere this guide says `python`.

---

## Step 2 — Download the App

**Option A — If you have Git installed:**
```
git clone https://github.com/YOUR-USERNAME/YOUR-REPO-NAME.git
cd YOUR-REPO-NAME
```

**Option B — Download as a ZIP (easier for beginners):**
1. On the GitHub page, click the green **Code** button
2. Click **Download ZIP**
3. Unzip the file somewhere easy to find (like your Desktop)
4. In your terminal, navigate into the folder:
   - **Mac**: `cd ~/Desktop/YOUR-FOLDER-NAME`
   - **Windows**: `cd C:\Users\YourName\Desktop\YOUR-FOLDER-NAME`

---

## Step 3 — Install Dependencies

This app uses a few open-source libraries. Install them all with one command:

```
pip install -r requirements.txt
```

This may take a minute or two. You'll see a lot of text scrolling — that's normal.

If you get a "pip not found" error, try:
```
pip3 install -r requirements.txt
```

---

## Step 4 — Add Your Email Address

SEC EDGAR (the source of all financial data) asks that tools identify themselves with a contact email. This is a courtesy requirement — your email will only be used if SEC needs to contact you about unusual usage.

1. Open the file `pull_cash_flow.py` in any text editor (Notepad on Windows, TextEdit on Mac, or any code editor)
2. Near the top, find this line:
   ```
   set_identity("your-email@example.com")  # Replace with your own email address
   ```
3. Replace `your-email@example.com` with your actual email address
4. Save the file

---

## Step 5 — Run the App

In your terminal (make sure you're still in the project folder), run:

```
python app.py
```

You should see something like:
```
 * Running on http://127.0.0.1:8080
```

---

## Step 6 — Open It in Your Browser

Open any web browser and go to:

**http://localhost:8080**

Type a U.S. stock ticker symbol (like `AAPL`, `MSFT`, or `PLAY`) into the search box and press Search. Data loads in a few seconds.

---

## Stopping the App

Go back to the terminal and press **Ctrl + C**. The app will stop.

To start it again later, repeat Step 5.

---

## Troubleshooting

**"python is not recognized" or "command not found"**
Try using `python3` instead of `python`. If that also fails, Python may not have installed correctly — repeat Step 1 and make sure to check "Add Python to PATH" on Windows.

**"pip is not recognized"**
Try `pip3`. If that fails, try `python -m pip install -r requirements.txt`.

**"Port 8080 is already in use"**
Something else is using that port. Open `app.py` in a text editor, find the last line:
```python
app.run(debug=True, port=8080)
```
Change `8080` to `8081` (or any other number), save, and run again. Then go to `http://localhost:8081` in your browser.

**The page loads but a ticker shows an error**
- Make sure the ticker is a U.S.-listed company (this tool uses SEC EDGAR, which covers U.S. filings only)
- Some very small companies or recent IPOs may have limited data
- Check that your email is set correctly in `pull_cash_flow.py` (Step 4)

**Data looks slow to load**
The app fetches live data from SEC's servers each time. The first load for a ticker typically takes 5–15 seconds depending on your internet connection and how many filings the company has.

---

## Notes

- **Data source**: All financial statement data comes from [SEC EDGAR](https://www.sec.gov/edgar), which contains official filings (10-K and 10-Q) for all U.S. public companies. Market cap and share price come from Yahoo Finance.
- **Local only**: This app runs entirely on your own computer. No data is sent anywhere except to SEC EDGAR and Yahoo Finance to fetch results.
- **Free to use**: All data sources used here are free. No API keys or subscriptions needed.
