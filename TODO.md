1. add X support, fetch, store X posts 
2. accept browser plugin's bookmark style drops to source box in the ui
3. encryption on vault guarded files
4. api encryption for MCP (later)
5. the project can be a MCP server for agents
6. in setup.sh, add logic when users choose not to use AI by passing API key input, it should show "draft still works well with index/search functions just w/o AI assistances"
7. the setup.sh should be able identify this is a new installation meaning all doc sources are empty vs an existing installation when ~/.draft/.doc_sources and vault are filled with files.
8. the setup.sh should have a logic to check sources.yaml and ~/.draft/.doc_sources and vault's consistency