# NUST Qalam Results Scraper

A Vibe Coded Python scraper that extracts student results from the NUST Qalam portal and generates a detailed markdown report with grade aggregates.

## Features

- Scrapes all enrolled courses from Qalam portal
- Extracts both Lecture and Lab module data
- Calculates weighted aggregates based on credit hours
- Generates a comprehensive markdown report with:
  - Overall summary table
  - Per-subject breakdown
  - Category-wise scores with weightage contributions

## Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) package manager
- Google Chrome browser

## Installation

1. Clone the repository:
   ```bash
   git clone <repo-url>
   cd qalam-aggregate-calculator
   ```

2. Install dependencies using uv:
   ```bash
   uv sync
   ```

3. Create a `.env` file in the project root with your Qalam credentials:
   ```env
   QALAM_USERNAME=your_registration_number
   QALAM_PASSWORD=your_password
   ```

## Usage

Run the scraper:
```bash
uv run python qalam_scraper.py
```

The scraper will:
1. Log in to the Qalam portal
2. Navigate to the results page
3. Scrape each course's gradebook
4. Generate `output.md` with the complete results report

## Output

The generated `output.md` contains:
- **Overall Summary**: Table with all courses, credit hours, and aggregates
- **Per Subject Details**: 
  - Module breakdown (Lecture/Lab)
  - Category scores (Quiz, Assignments, Mid Term, Final Term, etc.)
  - Individual assessment items with marks and percentages

## Credit Hour Weighting

For courses with both Lecture and Lab:
- Lecture weight = (total credits - 1) / total credits
- Lab weight = 1 / total credits

For example, a 3 credit hour course with lab:
- Lecture: 66.67% weight
- Lab: 33.33% weight

## Notes

- The scraper runs in headless Chrome mode
- Login credentials are never logged or stored beyond the `.env` file
