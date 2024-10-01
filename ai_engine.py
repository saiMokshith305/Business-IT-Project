from flask import Flask, request, jsonify
from openai import OpenAI
import psycopg2
import os

# Set your OpenAI API key (store securely in environment variables)
DATABASE_URL = os.environ.get('DATABASE_URL')
OPENAI_KEY = os.environ.get('OPENAI_KEY')

client = OpenAI(api_key=OPENAI_KEY)


app = Flask(__name__)

# Connect to PostgreSQL
conn = psycopg2.connect(DATABASE_URL, sslmode='require')

# Function to query OpenAI for parsing the search query
from openai import OpenAI

def query_openai(query):
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",  
        messages=[
            {"role": "system", "content": """
            You are an assistant that extracts and classifies keywords into specific database columns based on a user query. The columns are: 
            - reviews (e.g., 'best', 'top', 'recommended'), 
            - tool_type (categories like 'Collaboration', 'Content Creation'), 
            - learning_activities (like 'Critical Thinking', 'Communication Skills'), 
            - ease_of_use (like 'beginner', 'advanced'), 
            - name (name of the tool), 
            - description (description of the tool, including attributes like 'software architecture'). 

            Your task is to:
            1. Ignore natural language components (e.g., 'give', 'me', 'tools').
            2. Classify keywords into the appropriate database columns:
               - Keywords reflecting quality/feeling/trend etc (e.g., 'best', 'top') should be classified under reviews and description.
               - Keywords indicating purpose or function (e.g., 'designing') should be classified under tool_type, learning_activities, or description.
               - Specific features or attributes (e.g., 'software architecture') should be categorized under description, tool_type, or reviews.
               - If direct names of tools are included, classify them under name.
            3. Return the classified keywords with their corresponding columns in a structured format.

            Example Query: 'Give me the best tools for designing software architecture'
            Classified Output:
            - best → reviews, description
            - designing → tool_type, learning_activities, description
            - software architecture → description, tool_type, reviews
            """},
            {"role": "user", "content": f"Classify the following user query: '{query}' into the appropriate columns."}
        ],
        max_tokens=200,
        temperature=0.7
    )

    # Extract the result from OpenAI's response
    response_text = response.choices[0].message.content.strip()

    # Debug: Print the raw response from OpenAI
    print(f"Raw OpenAI Response: {response_text}")

    # Parse the response to get the classified keywords in JSON/dictionary format
    # Assuming OpenAI returns structured data in a format like:
    # "best → reviews, description\n designing → tool_type, learning_activities, description"
    classified_keywords = {}
    for line in response_text.split("\n"):
        if "→" in line:
            keyword, columns = line.split("→")
            keyword = keyword.strip().lstrip('-').strip()
            columns = [col.strip() for col in columns.split(",")]
            classified_keywords[keyword] = columns

    return classified_keywords


def query_db(classified_keywords):
    # Base SQL query
    sql = "SELECT * FROM tools WHERE "

    # A dictionary to group keywords by columns
    column_conditions = {
        "reviews": [],
        "tool_type": [],
        "learning_activities": [],
        "ease_of_use": [],
        "name": [],
        "description": []
    }

    # Group the keywords based on their classified columns
    for keyword, columns in classified_keywords.items():
        for column in columns:
            # Handle array columns differently
            if column in ["reviews", "tool_type", "learning_activities"]:
                column_conditions[column].append(f"%s ILIKE ANY({column})")
            else:
                column_conditions[column].append(f"{column} ILIKE %s")

    # Build the WHERE conditions for each column
    where_conditions = []

    for column, conditions in column_conditions.items():
        if conditions:
            # Join multiple conditions for the same column with OR
            column_condition = f"(" + " OR ".join(conditions) + ")"
            where_conditions.append(column_condition)

    # Combine all conditions with AND
    sql += " OR ".join(where_conditions) + ";"

    # # Debug: Print the SQL query
    # print(f"Constructed SQL Query: {sql}")

    # Prepare the parameters for the query
    params = []
    for keyword, columns in classified_keywords.items():
        for column in columns:
            if column in ["reviews", "tool_type", "learning_activities"]:
                params.append(f"%{keyword}%")  # For array columns
            else:
                params.append(f"%{keyword}%")  # For text columns

    cursor = conn.cursor()
    full_query = cursor.mogrify(sql, tuple(params))
    print(f"Constructed SQL Query: {full_query.decode('utf-8')}")
    # Execute the SQL query in PostgreSQL
    # cursor = conn.cursor()
    cursor.execute(sql, tuple(params))
    tools = cursor.fetchall()

    # Close the cursor
    cursor.close()

    return tools



@app.route('/api/search', methods=['POST'])
def search():
    data = request.get_json()
    query = data.get("query", "")

    # Query OpenAI to understand the search intent
    keywords = query_openai(query)

    # Query the database for matching tools
    tools = query_db(keywords)

    # Return the search results as JSON
    return jsonify({"tools":tools},{"keywords": keywords})

if __name__ == '__main__':
    app.run(debug=True)
