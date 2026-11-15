import os
import re
import pandas as pd
import psycopg2
import streamlit as st

st.set_page_config(
    page_title="Titanic PostgreSQL Learning App",
    page_icon="🚢",
    layout="wide"
)

st.title("Titanic Dataset: PostgreSQL + Streamlit")
st.caption("Explore SQL, database connectivity, and Titanic data.")


def get_db_config():
    return {
        "host": os.getenv("PGHOST", "localhost"),
        "port": int(os.getenv("PGPORT", "5432")),
        "dbname": os.getenv("PGDATABASE", "titanic_db"),
        "user": os.getenv("PGUSER", "titanic_app"),
        "password": os.getenv("PGPASSWORD", ""),
    }


def get_connection():
    config = get_db_config()

    if not config["password"]:
        raise ValueError("Database password is missing.")

    return psycopg2.connect(**config, connect_timeout=5)


def read_query(sql, params=None):
    conn = get_connection()

    try:
        conn.set_session(readonly=True, autocommit=False)

        with conn.cursor() as cursor:
            cursor.execute(sql, params)

            if cursor.description is None:
                raise ValueError("Query did not return results.")

            columns = [description[0] for description in cursor.description]
            rows = cursor.fetchall()

            return pd.DataFrame(rows, columns=columns)

    finally:
        conn.rollback()
        conn.close()
@st.cache_data(ttl=30)
def get_database_status():
    result = read_query("""
        SELECT
            current_database() AS database_name,
            current_schema() AS current_schema,
            version() AS postgres_version
    """)
    return result.iloc[0].to_dict()


try:
    db_status = get_database_status()
    st.success("Connected to PostgreSQL: " + db_status["database_name"])

except Exception as error:
    st.error("Could not connect to PostgreSQL.")
    st.info("Check database settings and password.")
    st.code(str(error))
    st.stop()


st.sidebar.title("Navigation")
st.sidebar.caption("Database: " + db_status["database_name"])
st.sidebar.caption("Schema: titanic_project")

if st.sidebar.button("Refresh database status"):
    get_database_status.clear()
    st.rerun()


dashboard_tab, explorer_tab, sql_tab, test_tab = st.tabs([
    "Dashboard",
    "Data Explorer",
    "SQL Lab",
    "Interactive Test"
])
with dashboard_tab:
    st.header("Passenger Dashboard")

    count_df = read_query("""
        SELECT COUNT(*) AS total_passengers
        FROM titanic_project.passengers
    """)

    total_passengers = int(count_df.iloc[0]["total_passengers"])

    survivor_df = read_query("""
        SELECT survived, COUNT(*) AS passenger_count
        FROM titanic_project.passengers
        GROUP BY survived
        ORDER BY survived
    """)

    survived_count = 0
    not_survived_count = 0

    for _, row in survivor_df.iterrows():
        if int(row["survived"]) == 1:
            survived_count = int(row["passenger_count"])
        elif int(row["survived"]) == 0:
            not_survived_count = int(row["passenger_count"])

    survival_rate = (
        survived_count / total_passengers * 100
        if total_passengers > 0 else 0
    )

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Total Passengers", f"{total_passengers:,}")
    col2.metric("Survived", f"{survived_count:,}")
    col3.metric("Did Not Survive", f"{not_survived_count:,}")
    col4.metric("Survival Rate", f"{survival_rate:.2f}%")

    st.divider()

    st.subheader("Survival by Passenger Class")

    class_df = read_query("""
        SELECT pclass, survived, COUNT(*) AS passenger_count
        FROM titanic_project.passengers
        GROUP BY pclass, survived
        ORDER BY pclass, survived
    """)

    class_pivot = class_df.pivot(
        index="pclass",
        columns="survived",
        values="passenger_count"
    ).fillna(0)

    class_pivot = class_pivot.rename(
        columns={0: "Did Not Survive", 1: "Survived"}
    )

    class_pivot.index.name = "Passenger Class"
    st.bar_chart(class_pivot)

    st.subheader("Survival by Sex")

    sex_df = read_query("""
        SELECT sex, survived, COUNT(*) AS passenger_count
        FROM titanic_project.passengers
        GROUP BY sex, survived
        ORDER BY sex, survived
    """)

    sex_pivot = sex_df.pivot(
        index="sex",
        columns="survived",
        values="passenger_count"
    ).fillna(0)

    sex_pivot = sex_pivot.rename(
        columns={0: "Did Not Survive", 1: "Survived"}
    )

    st.bar_chart(sex_pivot)

    st.subheader("Missing Values")

    missing_df = read_query("""
        SELECT
            COUNT(*) - COUNT(age) AS missing_age,
            COUNT(*) - COUNT(embarked) AS missing_embarked,
            COUNT(*) - COUNT(cabin) AS missing_cabin
        FROM titanic_project.passengers
    """)

    missing_report = pd.DataFrame({
        "Column": ["Age", "Embarked", "Cabin"],
        "Missing Values": [
            int(missing_df.iloc[0]["missing_age"]),
            int(missing_df.iloc[0]["missing_embarked"]),
            int(missing_df.iloc[0]["missing_cabin"])
        ]
    })

    st.dataframe(
        missing_report,
        use_container_width=True,
        hide_index=True
    )
with explorer_tab:
    st.header("Passenger Data Explorer")

    selected_class = st.multiselect(
        "Select Passenger Class",
        options=[1, 2, 3],
        default=[1, 2, 3]
    )

    selected_sex = st.multiselect(
        "Select Sex",
        options=["female", "male"],
        default=["female", "male"]
    )

    selected_survival = st.multiselect(
        "Select Survival Status",
        options=[0, 1],
        default=[0, 1],
        format_func=lambda x: "Survived" if x == 1 else "Did Not Survive"
    )

    row_limit = st.slider(
        "Maximum records to display",
        min_value=10,
        max_value=891,
        value=100,
        step=10
    )

    if st.button("Load Passenger Data"):
        if not selected_class or not selected_sex or not selected_survival:
            st.warning("Select at least one value in every filter.")
        else:
            query = """
                SELECT *
                FROM titanic_project.passengers
                WHERE pclass = ANY(%s)
                AND sex = ANY(%s)
                AND survived = ANY(%s)
                ORDER BY passengerid
                LIMIT %s
            """

            try:
                filtered_df = read_query(
                    query,
                    (selected_class, selected_sex, selected_survival, row_limit)
                )

                st.success(f"Retrieved {len(filtered_df)} records.")

                st.dataframe(
                    filtered_df,
                    use_container_width=True,
                    hide_index=True
                )

                st.download_button(
                    label="Download Displayed Data as CSV",
                    data=filtered_df.to_csv(index=False),
                    file_name="titanic_filtered_data.csv",
                    mime="text/csv"
                )

            except Exception as error:
                st.error("Unable to retrieve passenger data.")
                st.code(str(error))

    st.divider()
    st.subheader("Original Staging Data")

    if st.button("Load Staging Table Preview"):
        staging_df = read_query("""
            SELECT *
            FROM titanic_project.titanic_staging
            ORDER BY passengerid
            LIMIT 20
        """)

        st.dataframe(
            staging_df,
            use_container_width=True,
            hide_index=True
        )
with sql_tab:
    st.header("SQL Practice Lab")

    st.write("Execute read-only SELECT queries against the Titanic database.")

    example_queries = {
        "Show 10 passengers": """
            SELECT * FROM titanic_project.passengers LIMIT 10
        """,

        "Count passengers": """
            SELECT COUNT(*) AS total_passengers
            FROM titanic_project.passengers
        """,

        "Survival distribution": """
            SELECT survived, COUNT(*) AS passenger_count
            FROM titanic_project.passengers
            GROUP BY survived
            ORDER BY survived
        """,

        "Average age by class": """
            SELECT pclass, ROUND(AVG(age)::numeric, 2) AS average_age
            FROM titanic_project.passengers
            GROUP BY pclass
            ORDER BY pclass
        """,

        "Survival rate by sex": """
            SELECT sex, COUNT(*) AS total_passengers,
            SUM(survived) AS survivors,
            ROUND(100.0 * SUM(survived) / COUNT(*), 2)
            AS survival_percentage
            FROM titanic_project.passengers
            GROUP BY sex
        """,

        "Passengers with missing ages": """
            SELECT passengerid, name, sex, age, pclass
            FROM titanic_project.passengers
            WHERE age IS NULL
            ORDER BY passengerid
            LIMIT 50
        """
    }

    selected_example = st.selectbox(
        "Choose an example query",
        list(example_queries.keys())
    )

    sql_text = st.text_area(
        "SQL Query",
        value=example_queries[selected_example],
        height=220
    )

    if st.button("Run SQL Query"):
        cleaned = sql_text.strip().rstrip(";").strip()

        if not re.match(r"^(SELECT|WITH)\b", cleaned, re.IGNORECASE):
            st.error("Only SELECT and WITH queries are allowed.")
        elif ";" in cleaned:
            st.error("Enter one SQL statement at a time.")
        else:
            try:
                result_df = read_query(cleaned)

                st.success(
                    f"Query executed successfully. Rows returned: {len(result_df)}"
                )

                st.dataframe(
                    result_df,
                    use_container_width=True,
                    hide_index=True
                )

                st.download_button(
                    "Download Query Result",
                    data=result_df.to_csv(index=False),
                    file_name="sql_query_result.csv",
                    mime="text/csv"
                )

            except Exception as error:
                st.error("The query could not be executed.")
                st.code(str(error))

    st.divider()
    st.subheader("Practice Questions")

    st.markdown("""
    1. Display the first 20 passengers.
    2. Count passengers in each passenger class.
    3. Calculate the average fare.
    4. Find passengers whose age is missing.
    5. Calculate survival rates by sex.
    6. Count passengers by embarkation port.
    7. Find the maximum fare in each class.
    8. Compare survivors and non-survivors by class.
    """)
with test_tab:
    st.header("PostgreSQL and Streamlit Test")
    st.write("Answer all questions and submit the test to view your score.")

    questions = [
        {
            "question": "1. What is a database used for?",
            "options": [
                "Storing and managing data",
                "Designing slides",
                "Replacing an operating system",
                "Compiling Python code"
            ],
            "answer": 0
        },
        {
            "question": "2. What is a PostgreSQL schema?",
            "options": [
                "A CSV file",
                "A namespace for database objects",
                "A Python variable",
                "A password"
            ],
            "answer": 1
        },
        {
            "question": "3. Which command creates a schema?",
            "options": [
                "MAKE SCHEMA",
                "NEW SCHEMA",
                "CREATE SCHEMA",
                "INSERT SCHEMA"
            ],
            "answer": 2
        },
        {
            "question": "4. What does psql \\copy do?",
            "options": [
                "Deletes a table",
                "Imports or exports data through the client",
                "Creates a database",
                "Changes a password"
            ],
            "answer": 1
        },
        {
            "question": "5. How many original Titanic records exist?",
            "options": ["714", "889", "891", "204"],
            "answer": 2
        }
    ]

    with st.form("titanic_quiz"):
        answers = []

        for i, question in enumerate(questions):
            answer = st.radio(
                question["question"],
                options=list(range(len(question["options"]))),
                format_func=lambda j, q=question: q["options"][j],
                index=None,
                key=f"question_{i}"
            )
            answers.append(answer)

        submitted = st.form_submit_button("Submit Test")

    if submitted:
        if any(answer is None for answer in answers):
            st.warning("Answer all questions before submitting.")
        else:
            score = sum(
                1 for i, answer in enumerate(answers)
                if answer == questions[i]["answer"]
            )

            percentage = score / len(questions) * 100

            st.subheader("Test Results")
            st.metric("Correct Answers", f"{score} / {len(questions)}")
            st.metric("Percentage", f"{percentage:.2f}%")

            if percentage >= 80:
                st.success("Excellent work!")
            elif percentage >= 60:
                st.info("Good effort!")
            else:
                st.warning("Keep practicing!")
st.divider()

st.caption(
    "Titanic Dataset Learning Project | "
    "Python + Streamlit + PostgreSQL"
)
