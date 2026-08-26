# Step-by-Step Guide: Managing Scraper Websites

This guide explains how you, Angita, or Vikram sir can add and manage website sources in the Ekayan InfoPortal automated scraper pipeline. No coding or JSON knowledge is required!

---

## 📋 Table of Contents
1. [How to Access the Source Manager](#1-how-to-access-the-source-manager)
2. [Testing a New Website URL](#2-testing-a-new-website-url)
3. [Saving the Website to the Scraper](#3-saving-the-website-to-the-scraper)
4. [Removing a Scraper Source](#4-removing-a-scraper-source)
5. [Running the Scraper Immediately](#5-running-the-scraper-immediately)
6. [Troubleshooting Guide](#6-troubleshooting-guide)

---

## 1. How to Access the Source Manager

1. Open your Ekayan Admin Panel (`admin.html`) in your browser.
2. Enter the admin password (**admin123**) and click **Sign In**.
3. At the top of the page, click the **🌐 Manage Scrape Sources** tab.

You will see:
- **Left Panel:** The tool to test and add a new website.
- **Right Panel:** The list of websites currently configured for scraping.

---

## 2. Testing a New Website URL

Before saving a new website, you **must test it** to verify the scraper can read it.

1. In the **Source URL / Sitemap XML** input, paste the URL you want to scrape.
   - *Example 1 (Sitemap XML):* `https://example.com/sitemap.xml`
   - *Example 2 (Category page):* `https://example.com/scholarships`
2. **Optional (URL filter keywords):** If the site is a listing page, enter keywords (comma-separated) to narrow down the scraper. For example: `scholarship, admission`.
3. Click the **🔍 Test URL Compatibility** button.

### Understanding Test Results:

* **✅ Green (Compatibility Pass!):**
  The site is fully compatible! The tester will show:
  - Detected structure type (Sitemap vs. HTML Listing page).
  - A list of sample sub-pages discovered on that page.
  - The configuration section will automatically unlock below.

* **⚠️ Yellow (No Links Discovered):**
  The page loaded successfully, but the scraper couldn't find any relevant sub-links.
  - *What to do:* Try removing/changing your filter keywords, check if the URL is correct, or contact the developer if the site uses heavy JavaScript.

* **❌ Red (Analysis Failed / Connection Error):**
  The website actively blocked the scraper request or the local server is offline.
  - *What to do:* Make sure the server (`python server.py`) is running in the terminal.

---

## 3. Saving the Website to the Scraper

Once a test passes successfully:

1. **Source Display Name:** The system will auto-suggest a name. You can customize this (e.g. *AglaSem Entrance Exams*).
2. **Category Hint:** Select the default category for this site (*Scholarships*, *Admissions*, *Fellowships*, or *Job Leads*).
3. Click **💾 Save to Scraper**.
4. You will see a success message: `🎉 Scraper source saved successfully!`. The new site will appear in the table on the right.

---

## 4. Removing a Scraper Source

If a website is no longer active or yields irrelevant options:

1. Go to the **Configured Scrape Sources** table on the right side.
2. Locate the website you want to delete.
3. Click the red **🗑️ Remove** button.
4. Confirm the prompt. The website is removed and will not be scraped on the next scheduled run.

---

## 5. Running the Scraper Immediately

The scraper is scheduled to run daily in the background. However, if you just added a new website and want to test it immediately:

1. Switch to the **🤖 AI Review Queue** tab.
2. Click the **🔄 Run Scraper Now** button.
3. Wait for the success alert. The scraper will scan all websites (including your newly added ones) and show any new opportunities found directly in your review queue!

---

## 6. Troubleshooting Guide

* **Why is the "Save to Scraper" button not appearing?**
  You must successfully run the `🔍 Test URL Compatibility` button and get a green pass first.
* **Why did the test fail with a Connection Error?**
  Verify the server is running locally on your computer. You must start the server using `python server.py` in your terminal.
* **The test passed, but why did the scraper not extract any opportunities?**
  Our AI scraper filters out expired opportunities or listings not relevant to Indian students. The scraper worked correctly but didn't find any valid, open opportunities on those pages.
