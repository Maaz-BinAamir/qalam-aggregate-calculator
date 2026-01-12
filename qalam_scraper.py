"""
NUST Qalam Results Scraper
Scrapes student results from Qalam portal and generates a detailed markdown report.
"""

import os
import time
import re
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from dataclasses import dataclass, field


@dataclass
class AssessmentItem:
    """Single assessment (e.g., Quiz 1, Assignment 2)"""

    name: str
    max_marks: float
    obtained_marks: float
    class_average: float
    percentage: float


@dataclass
class AssessmentCategory:
    """Category like Quiz, Assignments, Mid Term, Final Term"""

    name: str
    weightage: float
    obtained_percentage: float
    is_lab_module: bool = False  # Whether this category is in a Lab module
    items: list[AssessmentItem] = field(default_factory=list)

    def is_exam(self) -> bool:
        """Check if this is an exam category (Mid/Final) - only applies to Lecture modules"""
        if self.is_lab_module:
            return False  # Lab modules don't use "highest marks" logic
        name_lower = self.name.lower()
        return "mid" in name_lower or "final" in name_lower or "ese" in name_lower

    @property
    def my_percentage(self) -> float:
        if not self.items:
            return self.obtained_percentage
        if self.is_exam():
            # For Lecture exams: use the item with highest max_marks
            best_item = max(self.items, key=lambda x: x.max_marks)
            return best_item.percentage
        # For everything else (including all Lab categories): average of all items
        return sum(item.percentage for item in self.items) / len(self.items)

    @property
    def class_avg_percentage(self) -> float:
        if not self.items:
            return 0.0
        if self.is_exam():
            # For Lecture exams: use the item with highest max_marks
            best_item = max(self.items, key=lambda x: x.max_marks)
            if best_item.max_marks == 0:
                return 0.0
            return (best_item.class_average / best_item.max_marks) * 100
        # For everything else: weighted average based on max marks
        total_class = sum(item.class_average for item in self.items)
        total_max = sum(item.max_marks for item in self.items)
        if total_max == 0:
            return 0.0
        return (total_class / total_max) * 100

    @property
    def my_weighted_contribution(self) -> float:
        return (self.weightage * self.my_percentage) / 100

    @property
    def class_weighted_contribution(self) -> float:
        return (self.weightage * self.class_avg_percentage) / 100


@dataclass
class ModuleResults:
    """Module like Lecture or Lab"""

    name: str
    categories: list[AssessmentCategory] = field(default_factory=list)

    @property
    def total_weightage(self) -> float:
        return sum(cat.weightage for cat in self.categories)

    @property
    def my_aggregate(self) -> float:
        return sum(cat.my_weighted_contribution for cat in self.categories)

    @property
    def class_aggregate(self) -> float:
        return sum(cat.class_weighted_contribution for cat in self.categories)


@dataclass
class SubjectResults:
    """A complete subject/course"""

    name: str
    code: str
    course_id: str
    credit_hours: float
    has_lab: bool = False
    modules: list[ModuleResults] = field(default_factory=list)

    @property
    def lecture_credits(self) -> float:
        return self.credit_hours - 1 if self.has_lab else self.credit_hours

    @property
    def lab_credits(self) -> float:
        return 1.0 if self.has_lab else 0.0

    @property
    def my_aggregate(self) -> float:
        if not self.modules:
            return 0.0
        total = 0.0
        for module in self.modules:
            weight = (
                self.lab_credits / self.credit_hours
                if module.name == "Lab"
                else self.lecture_credits / self.credit_hours
            )
            total += module.my_aggregate * weight
        return total

    @property
    def class_aggregate(self) -> float:
        if not self.modules:
            return 0.0
        total = 0.0
        for module in self.modules:
            weight = (
                self.lab_credits / self.credit_hours
                if module.name == "Lab"
                else self.lecture_credits / self.credit_hours
            )
            total += module.class_aggregate * weight
        return total


class QalamScraper:
    BASE_URL = "https://qalam.nust.edu.pk"

    def __init__(self):
        load_dotenv()
        self.username = os.getenv("QALAM_USERNAME")
        self.password = os.getenv("QALAM_PASSWORD")

        if not self.username or not self.password:
            raise ValueError("Set QALAM_USERNAME and QALAM_PASSWORD in .env")

        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")

        self.driver = webdriver.Chrome(options=chrome_options)
        self.wait = WebDriverWait(self.driver, 20)
        self.subjects: list[SubjectResults] = []

    def login(self):
        print("Logging in...")
        self.driver.get(f"{self.BASE_URL}/web/login?redirect=%2Fstudent%2Fresults")
        time.sleep(2)

        username_field = self.wait.until(
            EC.presence_of_element_located((By.NAME, "login"))
        )
        username_field.send_keys(self.username)

        password_field = self.driver.find_element(By.NAME, "password")
        password_field.send_keys(self.password)

        self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        time.sleep(5)

        if "/web/login" in self.driver.current_url:
            raise Exception("Login failed")
        print("Login successful!")

    def navigate_to_results(self):
        print("Going to results page...")
        self.driver.get(f"{self.BASE_URL}/student/results")
        time.sleep(3)

    def parse_float(self, text: str) -> float:
        try:
            return float(text.strip().replace(",", ""))
        except:
            return 0.0

    def get_course_links(self) -> list[dict]:
        courses = []
        seen_ids = set()

        cards = self.driver.find_elements(By.CSS_SELECTOR, "div.md-card.md-card-hover")

        for card in cards:
            try:
                link = card.find_element(
                    By.CSS_SELECTOR, "a[href*='/student/course/gradebook/']"
                )
                href = link.get_attribute("href")
            except:
                continue

            if not href:
                continue

            match = re.search(r"/gradebook/(\d+)", href)
            if not match:
                continue
            course_id = match.group(1)

            if course_id in seen_ids:
                continue
            seen_ids.add(course_id)

            try:
                name_elem = link.find_element(By.CSS_SELECTOR, "span.md-list-heading")
                code_elem = link.find_element(By.CSS_SELECTOR, "span.sub-heading")
                name = name_elem.text.strip()
                code = code_elem.text.strip()
            except:
                name = "Unknown"
                code = ""

            credit_hours = 3.0
            try:
                card_text = card.text
                match = re.search(r"Credit Hours\s*:\s*([\d.]+)", card_text)
                if match:
                    credit_hours = float(match.group(1))
            except:
                pass

            courses.append(
                {
                    "href": href,
                    "name": name,
                    "code": code,
                    "id": course_id,
                    "credits": credit_hours,
                }
            )
            print(f"  {code} - {name} ({credit_hours} CH)")

        return courses

    def scrape_gradebook_page(self, course_info: dict) -> SubjectResults:
        """Scrape a course gradebook page"""
        self.driver.get(course_info["href"])
        time.sleep(3)

        subject = SubjectResults(
            name=course_info["name"],
            code=course_info["code"],
            course_id=course_info["id"],
            credit_hours=course_info["credits"],
        )

        # Get number of panels - this tells us how many real tabs there are
        tab_panels = self.driver.find_elements(By.CSS_SELECTOR, "#tabs_anim1 > li")
        num_panels = len(tab_panels)

        print(f"    {num_panels} module(s) to process")

        if num_panels == 0:
            return subject

        # Get tab links - we need exactly num_panels of them
        # Find all tab links that are NOT in the responsive dropdown
        tab_ul = self.driver.find_element(By.CSS_SELECTOR, "ul.uk-tab")
        all_tab_links = tab_ul.find_elements(
            By.CSS_SELECTOR, ":scope > li:not(.uk-tab-responsive) > a"
        )

        # Only take the first num_panels links
        tab_links = all_tab_links[:num_panels]

        # Determine which tabs are Lab using JavaScript to get innerText
        # Use the specific tab that connects to #tabs_anim1
        tab_info = []
        for i in range(num_panels):
            # Use JavaScript to get the text from the tab header
            # Target the uk-tab that has data-uk-tab connecting to #tabs_anim1
            text = (
                self.driver.execute_script(f"""
                var tabUl = document.querySelector('ul.uk-tab[data-uk-tab*="tabs_anim1"]');
                if (tabUl) {{
                    var tabs = tabUl.querySelectorAll(':scope > li:not(.uk-tab-responsive)');
                    if (tabs[{i}]) {{
                        return tabs[{i}].innerText || tabs[{i}].textContent || '';
                    }}
                }}
                return '';
            """)
                or ""
            )
            text = " ".join(text.split())  # collapse whitespace
            upper = text.upper()
            is_lab = "-LAB)" in upper or "-LAB " in upper or upper.endswith("-LAB")
            if is_lab:
                subject.has_lab = True
            module_name = "Lab" if is_lab else "Lecture"
            tab_info.append({"name": module_name})
            debug_tail = text[-80:] if text else "(empty)"
            print(f"      Tab {i + 1}: '{debug_tail}' -> {module_name}")

        # Process each tab by index
        for idx, info in enumerate(tab_info):
            module_name = info["name"]

            print(f"      [{idx + 1}] {module_name}...")

            # Switch tabs by directly manipulating DOM classes
            # UIkit 2.x uses uk-active class on both tab headers and content panels
            try:
                self.driver.execute_script(f"""
                    // Get tab headers (specific to #tabs_anim1) and panels
                    var tabUl = document.querySelector('ul.uk-tab[data-uk-tab*="tabs_anim1"]');
                    var tabHeaders = tabUl ? tabUl.querySelectorAll(':scope > li:not(.uk-tab-responsive)') : [];
                    var tabPanels = document.querySelectorAll('#tabs_anim1 > li');
                    
                    // Remove active class from all headers and panels
                    tabHeaders.forEach(function(el) {{
                        el.classList.remove('uk-active');
                        el.setAttribute('aria-expanded', 'false');
                    }});
                    tabPanels.forEach(function(el) {{
                        el.classList.remove('uk-active');
                        el.setAttribute('aria-hidden', 'true');
                    }});
                    
                    // Add active class to the target header and panel
                    if (tabHeaders[{idx}]) {{
                        tabHeaders[{idx}].classList.add('uk-active');
                        tabHeaders[{idx}].setAttribute('aria-expanded', 'true');
                    }}
                    if (tabPanels[{idx}]) {{
                        tabPanels[{idx}].classList.add('uk-active');
                        tabPanels[{idx}].setAttribute('aria-hidden', 'false');
                    }}
                """)
                time.sleep(0.5)  # Brief wait for DOM update
            except Exception as e:
                print(f"          Tab switch failed: {e}")
                continue

            # Parse the panel at this index directly (don't rely on uk-active class)
            module = self.parse_panel_by_index(idx, module_name)

            if module.categories:
                subject.modules.append(module)
                items_count = sum(len(c.items) for c in module.categories)
                print(
                    f"          {len(module.categories)} categories, {items_count} items"
                )
                print(
                    f"          My: {module.my_aggregate:.2f}%, Class: {module.class_aggregate:.2f}%"
                )
            else:
                print(f"          No data found")

        return subject

    def parse_panel_by_index(self, idx: int, module_name: str) -> ModuleResults:
        """Parse a panel by its index (0-based)"""
        module = ModuleResults(name=module_name)
        is_lab = module_name == "Lab"

        # Find all panels and get the one at the specified index
        try:
            panels = self.driver.find_elements(By.CSS_SELECTOR, "#tabs_anim1 > li")
            if idx >= len(panels):
                print(
                    f"          Panel index {idx} out of range (only {len(panels)} panels)"
                )
                return module
            panel = panels[idx]
        except Exception as e:
            print(f"          Could not find panel at index {idx}: {e}")
            return module

        return self._parse_panel(panel, module, is_lab)

    def parse_active_panel(self, module_name: str) -> ModuleResults:
        """Parse the currently active panel"""
        module = ModuleResults(name=module_name)
        is_lab = module_name == "Lab"

        # Find the active panel - it has class uk-active
        try:
            active_panel = self.driver.find_element(
                By.CSS_SELECTOR, "#tabs_anim1 > li.uk-active"
            )
        except:
            print("          Could not find active panel")
            return module

        return self._parse_panel(active_panel, module, is_lab)

    def _parse_panel(
        self, panel, module: ModuleResults, is_lab: bool = False
    ) -> ModuleResults:
        """Parse a panel element and extract its data"""

        # Find table in the panel
        tables = panel.find_elements(By.CSS_SELECTOR, "table")
        if not tables:
            print("          No table found in panel")
            return module

        table = tables[0]

        # Expand all parent rows by clicking them
        parent_links = table.find_elements(By.CSS_SELECTOR, "tr.table-parent-row a")
        for link in parent_links:
            try:
                self.driver.execute_script("arguments[0].click();", link)
                time.sleep(0.15)
            except:
                pass

        time.sleep(0.3)

        # Parse rows
        all_rows = table.find_elements(By.CSS_SELECTOR, "tbody tr")
        current_category = None

        for row in all_rows:
            row_class = row.get_attribute("class") or ""

            if "table-parent-row" in row_class:
                if current_category and current_category.name:
                    module.categories.append(current_category)

                category_name = ""
                weightage = 0.0
                obtained_pct = 0.0

                try:
                    link = row.find_element(By.CSS_SELECTOR, "a")
                    full_text = link.text.strip()
                    lines = full_text.split("\n")
                    category_name = lines[0].strip()
                except:
                    pass

                try:
                    badge = row.find_element(By.CSS_SELECTOR, ".uk-badge")
                    badge_text = badge.text.strip()
                    match = re.search(r"([\d.]+)", badge_text)
                    if match:
                        weightage = float(match.group(1))
                except:
                    pass

                try:
                    tds = row.find_elements(By.CSS_SELECTOR, "td")
                    if len(tds) >= 2:
                        obtained_pct = self.parse_float(tds[1].text)
                except:
                    pass

                current_category = AssessmentCategory(
                    name=category_name,
                    weightage=weightage,
                    obtained_percentage=obtained_pct,
                    is_lab_module=is_lab,
                    items=[],
                )

            elif "table-child-row" in row_class:
                if "md-bg-blue-grey" in row_class:
                    continue
                if current_category is None:
                    continue

                tds = row.find_elements(By.CSS_SELECTOR, "td")
                if len(tds) >= 5:
                    name = tds[0].text.strip()
                    max_marks = self.parse_float(tds[1].text)
                    obtained = self.parse_float(tds[2].text)
                    class_avg = self.parse_float(tds[3].text)
                    percentage = self.parse_float(tds[4].text)

                    if name:
                        current_category.items.append(
                            AssessmentItem(
                                name=name,
                                max_marks=max_marks,
                                obtained_marks=obtained,
                                class_average=class_avg,
                                percentage=percentage,
                            )
                        )

        if current_category and current_category.name:
            module.categories.append(current_category)

        return module

    def scrape_all_results(self):
        print("\n" + "=" * 60)
        print("NUST Qalam Results Scraper")
        print("=" * 60)

        try:
            self.login()
            self.navigate_to_results()

            print("\nFinding courses...")
            courses = self.get_course_links()
            print(f"\n{len(courses)} courses found\n")

            for i, course in enumerate(courses, 1):
                print(
                    f"[{i}/{len(courses)}] {course['code']} - {course['name']} ({course['credits']} CH)"
                )
                try:
                    subject = self.scrape_gradebook_page(course)
                    if subject.modules:
                        self.subjects.append(subject)
                        print(
                            f"    => TOTAL: My {subject.my_aggregate:.2f}%, Class {subject.class_aggregate:.2f}%"
                        )
                except Exception as e:
                    print(f"    Error: {e}")
                    import traceback

                    traceback.print_exc()

        finally:
            self.driver.quit()

    def generate_markdown_report(self) -> str:
        lines = []
        lines.append("# NUST Qalam Results Report\n")
        lines.append("*Generated automatically*\n")
        lines.append("---\n")

        if not self.subjects:
            lines.append("No data scraped.\n")
            return "\n".join(lines)

        # Overall Summary
        lines.append("## Overall Summary\n")
        lines.append(
            "| Course | Code | Credits | Has Lab | My Aggregate | Class Aggregate |"
        )
        lines.append(
            "|--------|------|---------|---------|--------------|-----------------|"
        )
        for subj in self.subjects:
            lab_str = "Yes" if subj.has_lab else "No"
            lines.append(
                f"| {subj.name} | {subj.code} | {subj.credit_hours:.1f} | {lab_str} | **{subj.my_aggregate:.2f}%** | {subj.class_aggregate:.2f}% |"
            )
        lines.append("\n---\n")

        # Detailed breakdown
        for subj in self.subjects:
            lines.append(f"## {subj.code} - {subj.name}\n")

            if subj.has_lab:
                lines.append(
                    f"**Credit Hours:** {subj.credit_hours:.1f} ({subj.lecture_credits:.0f} Lecture + {subj.lab_credits:.0f} Lab)\n"
                )
            else:
                lines.append(
                    f"**Credit Hours:** {subj.credit_hours:.1f} (Lecture only)\n"
                )

            lines.append(
                f"### **Subject Aggregate: {subj.my_aggregate:.2f}% (Class Avg: {subj.class_aggregate:.2f}%)**\n"
            )

            for module in subj.modules:
                weight = (
                    (subj.lab_credits if module.name == "Lab" else subj.lecture_credits)
                    / subj.credit_hours
                    * 100
                )

                lines.append(f"### {module.name} ({weight:.1f}% of subject)\n")
                lines.append(
                    f"**Module Aggregate:** {module.my_aggregate:.2f}% (Class: {module.class_aggregate:.2f}%)\n"
                )
                lines.append(f"**Total Weightage:** {module.total_weightage:.1f}%\n")

                for cat in module.categories:
                    is_exam = cat.is_exam()
                    exam_note = (
                        " *(highest marks item used)*"
                        if is_exam and len(cat.items) > 1
                        else ""
                    )

                    lines.append(f"#### {cat.name}{exam_note}\n")
                    lines.append(f"- **Weightage:** {cat.weightage:.1f}%")
                    lines.append(
                        f"- **My %:** {cat.my_percentage:.2f}% → Contributes **{cat.my_weighted_contribution:.2f}%**"
                    )
                    lines.append(
                        f"- **Class Avg %:** {cat.class_avg_percentage:.2f}% → Contributes **{cat.class_weighted_contribution:.2f}%**"
                    )
                    lines.append("")

                    if cat.items:
                        lines.append(
                            "| Assessment | Max | Obtained | Class Avg | My % |"
                        )
                        lines.append(
                            "|------------|-----|----------|-----------|------|"
                        )
                        for item in cat.items:
                            marker = ""
                            if is_exam and len(cat.items) > 1:
                                best = max(cat.items, key=lambda x: x.max_marks)
                                if item == best:
                                    marker = " **[USED]**"
                            lines.append(
                                f"| {item.name}{marker} | {item.max_marks:.0f} | "
                                f"{item.obtained_marks:.2f} | {item.class_average:.2f} | "
                                f"{item.percentage:.2f}% |"
                            )
                        lines.append("")

                lines.append("")
            lines.append("---\n")

        return "\n".join(lines)

    def save_report(self, filename: str = "output.md"):
        report = self.generate_markdown_report()
        with open(filename, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\nSaved: {filename}")


def main():
    scraper = QalamScraper()
    try:
        scraper.scrape_all_results()
        scraper.save_report("output.md")

        print("\n" + "=" * 60)
        total_items = sum(
            sum(len(c.items) for c in m.categories)
            for s in scraper.subjects
            for m in s.modules
        )
        print(f"Done! {len(scraper.subjects)} subjects, {total_items} items")
        print("=" * 60)
    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
