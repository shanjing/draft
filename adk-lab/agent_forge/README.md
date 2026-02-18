## agent_forge

A scaffold utility to generate agent templates for ADK agents.

This tool is intended to build ADK agent layouts from a YAML file. It creates the following directory structure (using MarginCall as an example):

```
└── ProjectName
    ├── agent_tools
    │   ├── __init__.py
    │   ├── (all agent tools, MCP are here)
    │   └── server.py
    ├── check_env.py
    ├── main.py (CLI for user input)
    ├── agents
    │   ├── __init__.py
    │   ├── agent.py
    │   └── sub_agents
    └── tools (system tools: config, logging, runners, schemas, etc.)
        ├── __init__.py
        ├── config.py
        ├── logging_utils.py
        ├── runner_utils.py
        ├── save_artifacts.py
        └── schemas.py
```

agent_forge is WIP; the roadmap includes building and deploying agents in a CI/CD workflow.

Please refers to *.yaml files in this directory for various agents/patterns that agent_forge can create.
