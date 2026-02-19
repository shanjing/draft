# Multi-Agent in ADK 
This travel agent demonstrates a multi-agent system in ADK.

Usage:
```
python -m main run --help

python -m main run --input "Hi I'm Joe, I've never been to Paris, a 5-day trip would be great."
```

Multi_Agent workflow
* The root agent (supervisor_guard) takes user query and reviews
* Once approves delegate or call sub-agents to book trips and response to the user

Stateful implementations:
* Use a sqlite session service to store sessions for replay.
* Agents have memory for tools' to valid and enforce "only one trip per city" policy.

Standard Agent Module Design:
* cli/main for CLI options --input --debug --include_thoughts
* universal runner() for async execution of agents
* logging that dumps each event and session state update
* use session state to maintain key data

Extensive Debugging and CLI features:
* Switch between local llm/Ollama+LiteLlm and cloud based models
* Detailed log when -d --deubg flag is on
* Preflight Environment Verification

### Project Structure 
Below directory layout is required for ADK UI to work properly
```
travel_agent <--project's root directory
├── main.py <--cli and Runner
├── README.md
├── supervisor_guard <--root_agent
│   ├── __init__.py
│   ├── agent.py
│   └── sub_agents
│       ├── __init__.py
│       └── travel_planner <--sub_agents
└── tools <--tools for system, agents and helpers
    ├── __init__.py
    ├── config.py
    ├── db.py
    ├── logging_utils.py
    ├── schemas.py
    ├── travel_apps.py
    ├── travel_policy.py
    └── utilities.py
```
### Key Rules
* Variable Naming: 
  The ADK UI looks specifically for a variable named root_agent in the package root.
* Schema Peeking: 
  Tools must use Pydantic BaseModel in the signature (args: PolicyCheckInput)
  for the LLM to "see" the parameter descriptions.
* Directory Naming:
  The agent directory name must be the same as the agent's LlmAgent.name
* Bridge for importing: 
  __init__.py must have local import for ADK UI to import

### Core Components

1. ** Root Agent Package **
```
./supervisor_guard/agent.py
```
- Must be in the project root directory
- Must define a 'root_agent' python variable

2. **Sub-agents Directory**
```
./supervisor_guard/sub_agents/travel_agent/agent.py
./supervisor_guard/sub_agents/news_agent/agent.py
```
- Must be in the sub-directory root_agent's directory

3. **Tools**
Tools:
- check_travel_policy, record_visit
- get_5_day_weather, search_flights, search_hotels, record_visit,

4. **Importing Tools**
* import tools from the root agent
```
from tools.config import AI_MODEL
from tools.travel_policy import check_travel_policy
from .sub_agents.travel_planner.agent import (
    travel_agent,
)
```

5. **Schemas**
```
class PolicyCheckInput(BaseModel):
    user_id: str = Field(
        ..., description="The ID of the user requesting travel."
    )
    target_city: str = Field(
        ..., description="The city the user is requesting to travel to."
    )
```

## Mulit-Agent Patterns
### 1. Sub-Agent Delegation

The Supervisor hands the entire conversation to the Worker. 
The Worker talks directly to the user until it finishes.
```
root_agent = LlmAgent(
    name="supervisor_guard",
    model=AI_MODEL,
    tools=[
        check_travel_policy,
        sub_agents=[travel_agent, news_agent],
    ],
    ...
)
```
**Restriction**: 
The ADK built-in tools can not be used in a sub-agent.
Use AgentTool(below) instead.

### 2. Agent-as-a-Tool 

The Supervisor calls the Worker like a function.
The Worker returns data, and the Supervisor decides what to tell the user.
```
from google.adk.tools.agent_tool import AgentTool
root_agent = LlmAgent(
    name="supervisor_guard",
    model=AI_MODEL,
    tools=[
        check_travel_policy,
        AgentTool(agent=travel_agent)
    ],
    ...
)
```



