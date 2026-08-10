import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from playwright.sync_api import sync_playwright


URL = "https://m.attheraces.com/form/trainer/K-Scott/1194583"

OUTPUT = Path("entries.json")


def clean(value):
    if not value:
        return ""

    return re.sub(r"\s+", " ", value).strip()


def parse_date(value):
    value = clean(value)

    formats = [
        "%d %b %Y",
        "%d/%m/%Y",
        "%d %B %Y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass

    return None


def scrape():

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True
        )

        page = browser.new_page(
            viewport={
                "width": 1280,
                "height": 2000
            },

            locale="en-GB",

            user_agent=(
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/130 Safari/537.36"
            )
        )

        print("Opening At The Races...")

        response = page.goto(
            URL,
            wait_until="domcontentloaded",
            timeout=60000
        )

        if response is None:
            raise Exception(
                "No response received from At The Races"
            )

        print(
            f"HTTP status: {response.status}"
        )

        if response.status >= 400:
            raise Exception(
                f"At The Races returned HTTP {response.status}"
            )

        page.wait_for_timeout(5000)

        print(
            f"Page title: {page.title()}"
        )

        # -----------------------------------------------------
        # Look for the Future Entries section
        # -----------------------------------------------------

        body_text = page.locator("body").inner_text()

        if "Future Entries" not in body_text:
            raise Exception(
                "Could not find Future Entries on the page"
            )

        print(
            "Future Entries section found."
        )

        # -----------------------------------------------------
        # Extract tables
        # -----------------------------------------------------

        entries = []

        tables = page.locator("table")

        table_count = tables.count()

        print(
            f"Found {table_count} tables."
        )

        for table_index in range(table_count):

            table = tables.nth(
                table_index
            )

            table_text = clean(
                table.inner_text()
            )

            if not table_text:
                continue

            # We only want the Future Entries table.
            #
            # Different versions of At The Races can use
            # slightly different table headings, so we look
            # for several likely indicators.

            lower = table_text.lower()

            if not (
                "horse" in lower
                or "course" in lower
                or "race" in lower
            ):
                continue

            rows = table.locator("tr")

            row_count = rows.count()

            for row_index in range(
                row_count
            ):

                cells = rows.nth(
                    row_index
                ).locator(
                    "th, td"
                )

                cell_count = cells.count()

                if cell_count < 2:
                    continue

                values = []

                for cell_index in range(
                    cell_count
                ):

                    values.append(
                        clean(
                            cells.nth(
                                cell_index
                            ).inner_text()
                        )
                    )

                row = " | ".join(
                    values
                )

                print(
                    "ROW:",
                    row
                )

                # -------------------------------------------------
                # Attempt to identify fields
                # -------------------------------------------------

                date = ""
                time = ""
                course = ""
                horse = ""
                race = ""
                distance = ""
                jockey = ""

                for value in values:

                    # Date
                    if not date:

                        parsed = (
                            parse_date(value)
                        )

                        if parsed:
                            date = (
                                parsed.isoformat()
                            )

                    # Time
                    if (
                        not time
                        and re.fullmatch(
                            r"\d{1,2}:\d{2}",
                            value
                        )
                    ):
                        time = value

                    # Distance
                    if (
                        not distance
                        and re.search(
                            r"\b\d+(?:m|f|y)\b",
                            value,
                            re.I
                        )
                    ):
                        distance = value

                # -------------------------------------------------
                # Try extracting links
                # -------------------------------------------------

                links = rows.nth(
                    row_index
                ).locator("a")

                link_count = links.count()

                link_values = []

                for link_index in range(
                    link_count
                ):

                    link_text = clean(
                        links.nth(
                            link_index
                        ).inner_text()
                    )

                    href = (
                        links.nth(
                            link_index
                        ).get_attribute(
                            "href"
                        )
                    )

                    if link_text:
                        link_values.append(
                            {
                                "text": link_text,
                                "href": href or ""
                            }
                        )

                # -------------------------------------------------
                # Horse is usually a linked value
                # -------------------------------------------------

                for link in link_values:

                    text = link["text"]

                    if (
                        text
                        and text.lower()
                        not in [
                            "details",
                            "form",
                            "racecard"
                        ]
                    ):

                        # Don't mistake course/race links
                        # for horse names.

                        if (
                            not re.search(
                                r"\b(?:ayr|hamilton|thirsk|kempton|newcastle|"
                                r"musselburgh|catterick|yarmouth|lingfield|"
                                r"doncaster|leicester|redcar|southwell|"
                                r"wolverhampton|chelmsford)\b",
                                text,
                                re.I
                            )
                        ):

                            horse = text

                            break

                # -------------------------------------------------
                # Fallback positional parsing
                # -------------------------------------------------

                if not horse:

                    for value in values:

                        if (
                            value
                            and value != date
                            and value != time
                            and value != distance
                        ):

                            horse = value

                            break

                # -------------------------------------------------
                # Course
                # -------------------------------------------------

                known_courses = [
                    "Ayr",
                    "Hamilton",
                    "Thirsk",
                    "Musselburgh",
                    "Catterick",
                    "Redcar",
                    "Newcastle",
                    "Kempton",
                    "Southwell",
                    "Wolverhampton",
                    "Lingfield",
                    "Chelmsford",
                    "Yarmouth",
                    "Doncaster",
                    "Leicester",
                    "Ripon",
                    "Beverley",
                    "York",
                    "Haydock",
                    "Carlisle",
                    "Hexham",
                    "Perth",
                    "Kelso",
                ]

                for value in values:

                    for course_name in known_courses:

                        if (
                            value.lower()
                            == course_name.lower()
                        ):

                            course = (
                                course_name
                            )

                # -------------------------------------------------
                # Store candidate
                # -------------------------------------------------

                if (
                    date
                    and horse
                ):

                    entries.append(
                        {
                            "date": date,
                            "time": time,
                            "course": course,
                            "horse": horse,
                            "race": race,
                            "distance": distance,
                            "jockey": jockey,
                            "source": URL
                        }
                    )

        browser.close()

    # ---------------------------------------------------------
    # Filter next seven days
    # ---------------------------------------------------------

    today = datetime.now().date()

    end_date = (
        today +
        timedelta(days=7)
    )

    filtered = []

    for entry in entries:

        try:

            entry_date = datetime.strptime(
                entry["date"],
                "%Y-%m-%d"
            ).date()

        except ValueError:

            continue

        if (
            today
            <= entry_date
            < end_date
        ):

            filtered.append(
                entry
            )

    # ---------------------------------------------------------
    # IMPORTANT:
    #
    # DO NOT DEDUPLICATE.
    #
    # Every race remains a separate entry.
    # ---------------------------------------------------------

    filtered.sort(
        key=lambda x: (
            x["date"],
            x["time"],
            x["course"],
            x["horse"]
        )
    )

    result = {

        "trainer":
            "Katie Scott",

        "updated":
            datetime.utcnow().isoformat()
            + "Z",

        "source":
            URL,

        "count":
            len(filtered),

        "entries":
            filtered

    }

    OUTPUT.write_text(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    print(
        f"Saved {len(filtered)} entries."
    )


if __name__ == "__main__":
    scrape()
