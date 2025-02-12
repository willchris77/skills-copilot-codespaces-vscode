from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import Select
from bs4 import BeautifulSoup, NavigableString
import time
import csv
from datetime import date, timedelta, datetime
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementNotInteractableException


def get_cook_county_preforeclosures_selenium(start_date, end_date, max_pages=5, user_agent_list=None):
    """
    Scrapes pre-foreclosure (Lis Pendens) listings using Selenium.
    """

    service = ChromeService(executable_path=ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service)

    try:
        driver.get("https://crs.cookcountyclerkil.gov/")
        print("1. Got main page")

        # 2. Click "Advanced Search"
        WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.LINK_TEXT, "Advanced Search"))
        ).click()
        print("2. Clicked advanced search")

        # 3. Expand the "Document Type Search" accordion.
        WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Document Type Search')]"))
        ).click()
        print("3. Clicked accordion")

        # 4. Wait for the dropdown and option, then select "LIS PENDENS".
        select_element = WebDriverWait(driver, 20).until(
            EC.visibility_of_element_located((By.ID, "DocumentType"))
        )
        print("4. Dropdown present")
        select = Select(select_element)
        WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located((By.XPATH, "//select[@id='DocumentType']/option[@value='LISF']"))
        )
        select.select_by_value("LISF")
        print("5. Selected LISF")

        # 6. Wait for and fill date inputs (re-locating after dropdown selection).
        # --- CRITICAL: Ensure visibility and interactability BEFORE interaction ---
        date_from_input = WebDriverWait(driver, 30).until(
            EC.visibility_of_element_located((By.ID, "RecordedFromDate"))
        )
        date_from_input.location_once_scrolled_into_view  # Scroll into view
        if not date_from_input.is_enabled():
            print("Error: date_from_input is not enabled.")
            return []
        print("6a. Date From Input Located, Visible, and Enabled")

        date_to_input = WebDriverWait(driver, 30).until(
            EC.visibility_of_element_located((By.ID, "RecordedToDate"))
        )
        date_to_input.location_once_scrolled_into_view  # Scroll into view
        if not date_to_input.is_enabled():
            print("Error: date_to_input is not enabled.")
            return []
        print("6b. Date To Input Located, Visible, and Enabled")
            # Convert dates to MM/DD/YYYY format
        try:
            start_date_obj = datetime.strptime(start_date, "%Y-%m-%d")
            end_date_obj = datetime.strptime(end_date, "%Y-%m-%d")
            start_date_formatted = start_date_obj.strftime("%m/%d/%Y")
            end_date_formatted = end_date_obj.strftime("%m/%d/%Y")
        except ValueError:
            print("Error: Invalid date format. Please use YYYY-MM-DD.")
            return []

        # Use send_keys to enter the dates.
        date_from_input.send_keys(start_date_formatted)
        print(f"STEP 7a: Entered start date: {start_date_formatted}")
        date_to_input.send_keys(end_date_formatted)
        print(f"STEP 7b: Entered end date: {end_date_formatted}")

        # --- 8. Search Button (Combined Wait and Click - Most Robust) ---
        try:
            # Use a WebDriverWait with a lambda function to find and click in one step
            WebDriverWait(driver, 30).until(
                lambda d: d.find_element(By.XPATH, "//div[@id='searchPanelBody' and contains(@style, 'display: block')]//button[@type='submit' and contains(., 'Search')]").click()
                or True  #  "or True" is crucial for the lambda to work correctly.
            )
            print("STEP 8: Clicked Search")
        except TimeoutException:
            print("Search button click failed.")
            return []
        except NoSuchElementException:
            print("The correct search button could not be found using the refined XPath.")
            return []


        # 9. Wait for results table OR "no results"
        try:
            WebDriverWait(driver, 60).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div#result table.table"))
            )
            print("STEP 9: Table Found")
            table_found = True
        except TimeoutException:
            print("Table not found. Checking for 'No Results' message...")
            try:
                no_results_element = WebDriverWait(driver, 10).until(
                    EC.visibility_of_element_located((By.CSS_SELECTOR, "div.row.container-box strong"))
                )
                print("No results found.")
                table_found = False
            except TimeoutException:
                print("Neither table nor 'No Results' message found.")
                return []

        all_listings = []

        # 10. Extract data (only if table found)
        if table_found:
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            all_listings.extend(extract_table_data(soup))

        # --- Pagination (ONLY if results were found) ---
        if table_found:
            for page_num in range(2, max_pages + 1):
                try:
                    # Find and click "Next"
                    next_button = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.LINK_TEXT, "Next"))
                    )
                    next_button.click()
                    print(f"STEP 11: Clicked Next (Page {page_num})")

                    # Wait for *new* table
                    WebDriverWait(driver, 20).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "div#result table.table"))
                    )
                    soup = BeautifulSoup(driver.page_source, 'html.parser')
                    all_listings.extend(extract_table_data(soup))
                    print(f"Scraped page {page_num}")

                except Exception as e:
                    print(f"Error on page {page_num}: {e}")
                    break
        # --- End of Pagination ---

        return all_listings

    except ElementNotInteractableException as e:
        print(f"Element not interactable error: {e}")
        return []
    except Exception as e:  # Catch ANY exception during scraping
        print(f"An error occurred: {e}")
        return []  # Return an empty list on error
    finally:
        driver.quit()

def extract_table_data(soup):
    """Extracts data from the HTML table."""
    import requests
    listings = []
    table = soup.find('div', id='result').find('table', class_='table')

    if table:
        rows = table.find_all('tr')[1:]  # Skip header row
        for row in rows:
            cells = row.find_all('td')
            if len(cells) > 10:
                listing_data = {}
                try:
                    # --- View Doc URL ---
                    view_doc_link = cells[1].find('a', href=True)
                    listing_data['view_doc_url'] = requests.compat.urljoin("https://crs.cookcountyclerkil.gov/", view_doc_link['href']) if view_doc_link else "N/A"

                    # --- Doc Number, Doc Recorded, etc. ---
                    listing_data['doc_number'] = get_cell_text(cells[2])
                    listing_data['doc_recorded'] = get_cell_text(cells[3])
                    listing_data['doc_executed'] = get_cell_text(cells[4])
                    listing_data['doc_type'] = get_cell_text(cells[5])
                    listing_data['consid_amt'] = get_cell_text(cells[6])
                    listing_data['first_grantor'] = get_cell_text(cells[7])
                    listing_data['first_grantee'] = get_cell_text(cells[8])
                    listing_data['assoc_doc_num'] = get_cell_text(cells[9])
                    listing_data['first_pin'] = get_cell_text(cells[10])
                    listings.append(listing_data)

                except IndexError:
                    print("Error: Not enough cells in row. Skipping.")
                    continue
                except Exception as e:
                    print("Error in extract_table_data:", e)
                    continue
    return listings

def get_cell_text(cell):
    """Extracts text from a cell, handling whitespace."""
    text_content = ""
    for child in cell.contents:
        if isinstance(child, NavigableString):
            text_content += child.strip()
    return text_content

if __name__ == "__main__":
    # USE A DATE RANGE WITH KNOWN RESULTS - for testing
    start_date = "2024-01-17"
    end_date = "2024-01-18"
    max_pages = 5  # Adjust as needed

    results = get_cook_county_preforeclosures_selenium(start_date, end_date, max_pages)

    if results:
        # Write to CSV
        with open("output.csv", "w", newline="", encoding="utf-8") as csvfile:
            fieldnames = ['doc_number', 'doc_recorded', 'doc_executed', 'doc_type', 'consid_amt',
                          'first_grantor', 'first_grantee', 'assoc_doc_num', 'first_pin', 'view_doc_url']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for listing in results:
                writer.writerow(listing)
        print("Data written to output.csv")
    else:
        print("No pre-foreclosure data retrieved.")
