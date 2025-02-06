import json
import time
import requests
import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

BASE_URL = "https://paperswithcode.com"


def setup_driver():
    """
    Sets up the Selenium WebDriver (Chrome) with headless option.
    """
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    driver = webdriver.Chrome(options=options)
    driver.maximize_window()
    return driver


def extract_text_from_page(driver):
    """
    Extracts and returns the paper title and abstract text from the current driver page.
    Returns a tuple (title, text) or empty string on failure.
    """
    try:
        # Wait for the abstract element to be present
        abstract_div = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.paper-abstract"))
        )
        title_div = driver.find_element(By.CSS_SELECTOR, "div.paper-title")
        title = title_div.find_element(By.TAG_NAME, "h1")
        col_div = abstract_div.find_element(By.CSS_SELECTOR, "div.col-md-12")
        p_elem = col_div.find_element(By.TAG_NAME, "p")
        return title.text.strip(), p_elem.text.strip()
    except Exception as e:
        print("Error extracting text:", e)
        return ""


def process_black_links(driver):
    """
    Processes all black-links in the page.
    Opens each link in a new tab to extract title and abstract text.
    Returns a dictionary containing lists of titles and texts.
    """
    extracted_texts = {"title": [], "text": []}
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.black-links a"))
        )
        link_elements = driver.find_elements(By.CSS_SELECTOR, "div.black-links a")
        urls = []
        for elem in link_elements:
            href = elem.get_attribute("href")
            if not href.startswith("http"):
                href = BASE_URL + href
            urls.append(href)

        original_window = driver.current_window_handle
        for url in urls:
            driver.execute_script("window.open(arguments[0]);", url)
            driver.switch_to.window(driver.window_handles[-1])
            title, text = extract_text_from_page(driver)
            print("Paper Title:", title)
            print("Extracted Text:", text)
            extracted_texts["title"].append(title)
            extracted_texts["text"].append(text)
            driver.close()
            driver.switch_to.window(original_window)
            time.sleep(1)
    except Exception as e:
        print("Error processing black-links:", e)
    return extracted_texts


def process_method_image(driver, method_image_url):
    """
    Processes a single method_image URL.
    Navigates through up to 10 pagination steps and collects black-links data.
    Returns a list of extracted titles and texts.
    """
    extracted_titles_texts = []
    driver.get(method_image_url)
    time.sleep(2)  # Wait for page load

    page_counter = 0
    while page_counter < 10:
        extracted_contents = process_black_links(driver)
        extracted_titles_texts.append(extracted_contents)
        try:
            # Wait and click next page button if available
            next_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, "li.paginate_button.page-item.next")
                )
            )
            ActionChains(driver).move_to_element(next_button).click().perform()
            time.sleep(2)
            page_counter += 1
            # If no active next button, break out on disabled
            if driver.find_elements(
                By.CSS_SELECTOR, "li.paginate_button.page-item.next.disabled"
            ):
                break
        except Exception as e:
            print("No additional page or error clicking next:", e)
            break
    return extracted_titles_texts


def process_topic_link(driver, topic_url):
    """
    Processes a given topic URL.
    Finds method_image div elements and processes each method_image link.
    Returns a dictionary mapping each method image URL to the extracted texts.
    """
    results = {}
    driver.get(topic_url)
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.method-image"))
        )
    except Exception as e:
        print("Error waiting for method-image elements:", e)
        return results

    method_divs = driver.find_elements(By.CSS_SELECTOR, "div.method-image")[:20]
    method_links = []
    for div in method_divs:
        try:
            a_tag = div.find_element(By.TAG_NAME, "a")
            href = a_tag.get_attribute("href")
            if not href.startswith("http"):
                href = BASE_URL + href
            method_links.append(href)
        except Exception as e:
            print("Error extracting method_image link:", e)

    for link in method_links:
        print("Processing method image link:", link)
        titles_texts = process_method_image(driver, link)
        results[link] = titles_texts
    return results


def get_topic_method_info(topic_name, card, methods_list):
    """
    Given a topic name and card element, extracts topic information,
    further scraping additional method info if available, and appends to methods_list.
    Returns the topic description if available.
    """
    topic_link = BASE_URL + card.find("a")["href"]
    topic_response = requests.get(topic_link)
    topic_soup = BeautifulSoup(topic_response.content, "html.parser")
    description_div = topic_soup.find("div", class_="description-content")
    description = description_div.text.strip() if description_div else None

    method_content_div = topic_soup.find("div", class_="method-content")
    if method_content_div:
        table = method_content_div.find("table")
        if table:
            rows = table.find("tbody").find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                cols = [ele.text.strip() for ele in cols]
                if len(cols) >= 3:
                    if "\n\n\n" in cols[0]:
                        method_name, paper = cols[0].split("\n\n\n", 1)
                    else:
                        method_name, paper = cols[0], None
                    methods_list.append(
                        {
                            "topic_name": topic_name,
                            "method": method_name.strip(),
                            "year": cols[1],
                            "num_papers": cols[2],
                            "paper_name": paper,
                        }
                    )
    return description


def fetch_initial_data():
    """
    Uses requests and BeautifulSoup to fetch the main page and build extracted_info and methods lists.
    Returns a tuple (extracted_info, methods).
    """
    url = f"{BASE_URL}/methods"
    response = requests.get(url)
    soup = BeautifulSoup(response.content, "html.parser")

    extracted_info = []
    methods = []
    topic_groups = soup.find_all("div", class_="row task-group-title")

    for group in topic_groups:
        ml_field = group.find("h4").text.strip()
        card_deck = group.find_next("div", class_="card-deck card-break infinite-item")
        print("-", ml_field)
        if card_deck:
            for card in card_deck.find_all("div", class_="card"):
                topic_name = card.find("h1").text.strip()
                print("---", topic_name)
                # Call the helper to extract additional topic details
                topic_desc = get_topic_method_info(topic_name, card, methods)
                extracted_info.append(
                    {
                        "topic_name": topic_name,
                        "ml_field": ml_field,
                        "num_methods": card.find("div", class_="text-muted")
                        .find("span")
                        .next_sibling.strip()
                        .split()[0],
                        "num_papers": card.find_all("div", class_="text-muted")[1]
                        .text.strip()
                        .split()[0],
                        # "topic_description": topic_desc,  # Uncomment if needed
                        "topic_link": BASE_URL + card.find("a")["href"],
                    }
                )
    return extracted_info, methods


def save_results(filename, data):
    """
    Saves the data dictionary to a JSON file.
    Parameters:
        filename: Name of the file to save data.
        data: Dictionary containing scraped results.
    """
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print(f"Scraping results saved to {filename}")
    except Exception as e:
        print("Error saving results:", e)


def main():
    """
    Main function to perform web scraping and save the extracted results persistently.
    """
    # Fetch initial topics and methods using requests and BeautifulSoup
    extracted_info, methods = fetch_initial_data()
    overall_results = {}

    # Setup Selenium driver and process each topic link to extract detailed info
    driver = setup_driver()
    try:
        for index, item in enumerate(extracted_info):
            topic_url = item.get("topic_link")
            if topic_url:
                print(f"Processing topic {index+1}: {topic_url}")
                topic_results = process_topic_link(driver, topic_url)
                overall_results[topic_url] = topic_results
                time.sleep(2)
            else:
                print(f"Topic link missing at index {index}")
    finally:
        driver.quit()

    # Optionally, you can convert DataFrames if needed
    df_topics = pd.DataFrame(extracted_info)
    df_methods = pd.DataFrame(methods)

    # Prepare a final result object including DF details if needed (here we only include overall_results)
    final_data = {
        "topics_info": extracted_info,
        "methods_info": methods,
        "detailed_results": overall_results,
    }

    # Save results to a JSON file
    save_results("scraping_results.json", final_data)

    print("Scraping completed.")


if __name__ == "__main__":
    main()
