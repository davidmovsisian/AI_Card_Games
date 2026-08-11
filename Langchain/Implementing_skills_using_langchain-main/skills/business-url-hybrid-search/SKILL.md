---
name: business-url-hybrid-search
description: Trigger this skill when a user needs to locate the official website URL for a specific business using its name and physical address. Use this for data enrichment, entity resolution, or verification tasks across industries like hospitality, retail, banking, and aviation. This skill performs a hybrid search (SerpAPI + DataForSEO) to cross-reference data and ensure high-accuracy URL discovery.
---

# Business URL Hybrid Search

## Overview
The `business-url-hybrid-search` skill is a specialized entity resolution tool designed to bridge the gap between physical business presence and digital identity. By utilizing a hybrid approach—leveraging both SerpAPI (Google Search) and DataForSEO—it locates the official website of a company based on its name and physical address. This dual-verification method significantly reduces false positives, distinguishing between official corporate sites, specific franchise location pages, and third-party directories.

## Automatic Processing
This skill relies on an underlying Python script to execute the API calls. The LLM must structure the input correctly for the script to function.

### Input Schema
The script expects a JSON payload containing:
```json
{
  "business_name": "string",
  "address": "string (full address including city/state/zip preferred)",
  "country_code": "string (optional, default 'US')"
}
```

### Script Execution
The system executes `business_url_hybrid_search.py`. The script performs the following logic:
1.  Queries SerpAPI with the business name and address.
2.  Queries DataForSEO with the same parameters.
3.  Compares results to identify the most probable official domain.
4.  Filters out common directory sites (Yelp, YellowPages, TripAdvisor) unless requested otherwise.

### Output Schema
The script returns a JSON object:
```json
{
  "status": "success | not_found | error",
  "url": "https://www.example.com",
  "confidence": "high | medium | low",
  "source": "serpapi | dataforseo | hybrid_match",
  "metadata": {
    "title": "Page Title",
    "snippet": "Description from search result"
  }
}
```

## Core Capabilities
1.  **Hybrid Verification:** Cross-references results from two distinct search indices to maximize accuracy.
2.  **Location Disambiguation:** Uses specific address details to distinguish between franchise locations (e.g., a specific Hilton Garden Inn vs. the global Hilton homepage).
3.  **Directory Filtering:** Automatically attempts to bypass aggregator sites to find the direct business owner's URL.
4.  **Resilient Search:** Handles minor typos in business names or incomplete address formats.

## Workflow

### Step 1: Input Extraction and Validation
1.  Analyze the user's prompt to identify the **Business Name** and **Physical Address**.
2.  **CRITICAL:** If the address is missing or too vague (e.g., just "Chicago"), ask the user for more specific location details (Street, Zip Code) before proceeding, unless the business is a unique global entity.
3.  If the address is present, proceed to Step 2.

### Step 2: Construct Script Arguments
1.  Format the extracted data into the required JSON structure.
2.  Ensure the address string is concatenated into a single line if provided in parts.

### Step 3: Execute Search
1.  Call the `business_url_hybrid_search` tool/script.
2.  Wait for the JSON response.

### Step 4: Result Analysis
1.  **Check Status:**
    *   If `status` is "success", proceed to Step 5.
    *   If `status` is "not_found", inform the user that no official website could be confidently identified.
    *   If `status` is "error", report the technical difficulty.
2.  **Check Confidence:**
    *   If `confidence` is "low", flag this in the final response (e.g., "I found a potential match, but please verify...").

### Step 5: Final Output Generation
1.  Present the URL clearly.
2.  If the user requested a specific format (e.g., CSV, Markdown link), format accordingly.
3.  If the result is a specific location page (e.g., `.../locations/chicago`), mention that it is the specific branch page.

## Usage Patterns

### Pattern 1: Direct Lookup
**User:** "Find the website for Joe's Pizza at 123 Main St, New York."
**Action:** Extract "Joe's Pizza" and "123 Main St, New York". Run script. Return URL.

### Pattern 2: Batch Processing (Iterative)
**User:** "Get URLs for these three companies: [List of Name/Address pairs]."
**Action:**
1.  Acknowledge the list.
2.  Iterate through the list, running the workflow for **each** item individually.
3.  Compile the results into a table or list format.

### Pattern 3: Verification
**User:** "Is www.hilton.com the right site for the Hilton at 555 State St?"
**Action:** Run the search for "Hilton" at "555 State St". Compare the returned URL with the user's provided URL. Confirm if they match or if a more specific location page exists.

## Error Handling

| Error Type | Likely Cause | User Message |
| :--- | :--- | :--- |
| **Missing Address** | User provided name only. | "To ensure I find the correct website, could you please provide the street address or city for [Business Name]?" |
| **Not Found** | Business is new, closed, or has no web presence. | "I searched multiple databases but could not locate an official website for [Business Name] at that address. They may rely on social media or third-party directories." |
| **API Error** | Rate limits or connectivity issues. | "I encountered a technical issue while searching. Please try again in a moment." |
| **Ambiguous Result** | Multiple businesses at the same address (e.g., a mall). | "I found a few potential websites associated with this address. The most likely match is [URL]. Please verify it is the correct entity." |

## Output Formatting

### Short Content (Chat)
> **Website Found:** [https://www.hilton.com/en/hotels/chi-garden-inn](https://www.hilton.com/en/hotels/chi-garden-inn)

### Medium Content (Report)
> **Business:** Hilton Garden Inn
> **Address:** 123 Main Street, Chicago
> **Website:** [Link](https://www.hilton.com/en/hotels/chi-garden-inn)
> **Note:** This appears to be the direct location page for this specific branch.

### Long Content (Detailed Analysis)
> I have located the website for **Hilton Garden Inn** in Chicago.
>
> *   **Official URL:** https://www.hilton.com/en/hotels/chi-garden-inn
> *   **Confidence:** High (Verified via SerpAPI and DataForSEO)
> *   **Source Match:** The domain matches the corporate Hilton structure, and the page metadata references the "123 Main Street" location.
>
> Let me know if you need to find contact information from this page.

## Best Practices
1.  **Specificity is Key:** Always prefer full addresses (Street + City + State + Zip) over partial ones to avoid false positives with franchises.
2.  **Official vs. Directory:** The skill prioritizes official domains. If the user *wants* a Yelp or TripAdvisor link, they must explicitly ask for it; otherwise, the skill filters these out.
3.  **Protocol Handling:** Always return the URL with the protocol (`http://` or `https://`) to ensure it is clickable in the UI.
4.  **No Hallucinations:** If the script returns `null` or empty results, do not invent a URL based on the company name (e.g., do not guess `www.companyname.com`). State that it was not found.