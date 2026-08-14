import questionary as qt

tools = [
    {
        "type": "web_search_20260209",
        "name": "web_search",
        "max_uses": 5
    },
    {
        "name": "ask_user_question",
        "description": "Ask a question to the user to clarify ambigous prompts, Use this almost every prompt",
        "input_schema": {
            "type": "object",
            "required": ["question", "choices"],
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The question to ask the user"
                },
                "choices": {
                    "type": "array",
                    "description": "Short answer options. An 'other' field is always shown as well.",
                    "items": {"type": "string"},
                    "minItems": 1
                },
                "max_answers": {
                    "type": "integer",
                    "description": "Max allowed choices the user can provide, default: 1"
                }
            }
        } 
    }
]

def ask_user_question(question: str, choices: list, max_answers: int = 1):
    choices.append("Other")
    response = qt.checkbox(
        question,
        choices,
        validate=lambda sel: True if len(sel) <= max_answers else f"Pick at most {max_answers}"
    ).ask()

    if response[0] == "Other":
        return qt.text("What else?").ask()
    else:
        return response