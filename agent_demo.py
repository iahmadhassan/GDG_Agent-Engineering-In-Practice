import json
import os

from dotenv import load_dotenv
from openai import OpenAI


# Load variables from a .env file in the current project directory.
load_dotenv()

# OpenRouter routes this alias to an available free model that supports tools.
MODEL = "openrouter/free"

# The agent keeps its task board in memory while it runs.
task_board = []
PLAN_FILE = "study_plan.json"


def create_client():
    """Create an OpenAI-compatible client connected to OpenRouter."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is missing. Add it to your .env file."
        )

    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )


# -----------------------------------------------------------------------------
# Tools: these are ordinary Python functions that the model can request.
# -----------------------------------------------------------------------------

def add_task(title: str, duration_minutes: int):
    """Add a study task to the task board."""
    if not title.strip() or duration_minutes <= 0:
        return {"ok": False, "error": "Invalid task details."}

    task = {
        "title": title,
        "duration_minutes": duration_minutes,
    }
    task_board.append(task)

    return {
        "ok": True,
        "added": task,
        "total_tasks": len(task_board),
    }


def save_plan():
    """Save the current task board to a JSON file."""
    total_minutes = sum(task["duration_minutes"] for task in task_board)
    plan = {
        "tasks": task_board,
        "total_minutes": total_minutes,
    }

    with open(PLAN_FILE, "w", encoding="utf-8") as file:
        json.dump(plan, file, indent=4)

    return {
        "ok": True,
        "message": "Study plan saved successfully.",
        "file": PLAN_FILE,
        "total_minutes": total_minutes,
    }


def read_plan():
    """Read the saved plan so the agent can verify it."""
    if not os.path.exists(PLAN_FILE):
        return {"ok": False, "error": "Plan does not exist."}

    with open(PLAN_FILE, "r", encoding="utf-8") as file:
        plan = json.load(file)

    return {
        "ok": True,
        "verified": True,
        "plan": plan,
    }


# OpenAI-compatible Chat Completions function tool definitions.
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "add_task",
            "description": "Add a study task with its duration in minutes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "duration_minutes": {"type": "integer"},
                },
                "required": ["title", "duration_minutes"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_plan",
            "description": "Save all created tasks to study_plan.json.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_plan",
            "description": "Read the saved plan to verify its tasks and total duration.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        },
    },
]

AVAILABLE_TOOLS = {
    "add_task": add_task,
    "save_plan": save_plan,
    "read_plan": read_plan,
}


def execute_tool(name, arguments):
    """Run a requested tool and return its result."""
    print(f"\n[TOOL CALL] {name}")
    print(f"[ARGUMENTS] {arguments}")

    function = AVAILABLE_TOOLS.get(name)
    if function is None:
        return {"ok": False, "error": f"Unknown tool: {name}"}

    try:
        result = function(**arguments)
        print(f"[TOOL RESULT] {result}")
        return result
    except Exception as error:
        result = {"ok": False, "error": str(error)}
        print(f"[TOOL RESULT] {result}")
        return result


# -----------------------------------------------------------------------------
# Agent loop
# -----------------------------------------------------------------------------

SYSTEM_PROMPT = """
You are an autonomous study-planning agent.

Accomplish the user's goal using the available tools:
1. Break the goal into individual study tasks.
2. Call add_task for each task.
3. Call save_plan to save the completed plan.
4. Call read_plan to verify the saved tasks and total duration.
5. Report completion only after successful verification.

Never claim an action succeeded unless its tool returned a successful result.
Give a concise final summary.
""".strip()


def run_agent(goal):
    client = create_client()

    print("\n========== AGENT STARTED ==========")
    print(f"[USER GOAL] {goal}")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": goal},
    ]

    max_steps = 12

    for step in range(max_steps):
        print(f"\n[AGENT] Thinking... Step {step + 1}")

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            parallel_tool_calls=False,
        )

        assistant_message = response.choices[0].message
        tool_calls = assistant_message.tool_calls or []

        if not tool_calls:
            print("\n========== FINAL RESPONSE ==========")
            print(assistant_message.content or "The agent returned no text response.")
            return

        # Keep the assistant's tool request in the conversation history.
        messages.append(assistant_message.model_dump(exclude_none=True))

        for tool_call in tool_calls:
            try:
                arguments = json.loads(tool_call.function.arguments or "{}")
                result = execute_tool(tool_call.function.name, arguments)
            except (json.JSONDecodeError, TypeError) as error:
                result = {"ok": False, "error": f"Invalid tool arguments: {error}"}

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result),
                }
            )

    print("[AGENT] Maximum steps reached. Stopping.")


DEFAULT_GOAL = """
Create a focused 3-hour study plan:
- Python practice: 90 minutes
- Database Systems revision: 60 minutes
- Break: 30 minutes

Save the plan and verify that the total duration is exactly 180 minutes.
""".strip()


if __name__ == "__main__":
    print("===================================")
    print("       MY FIRST AI AGENT")
    print("===================================")

    goal = input("\nEnter your goal (press Enter for demo): ").strip()
    if not goal:
        goal = DEFAULT_GOAL

    run_agent(goal)