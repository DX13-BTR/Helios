import os
import sys
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "core_py", "core", "llm")
    ),
)

from core.llm.route_prompt import routePrompt

prompt = "Given how tired I am and what's coming up, what should I prioritise?"

result = routePrompt(prompt, model="gpt-4")

print("\n📬 Final response:")
print(result)
