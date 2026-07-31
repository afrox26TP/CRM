# DokladFlow workspace instructions

- [x] Verify that the copilot-instructions.md file in the .github directory is created.
- [x] Clarify Project Requirements
- [x] Scaffold the Project
- [x] Customize the Project
- [x] Install Required Extensions — no additional extensions required
- [x] Compile the Project
- [x] Create and Run Task
- [x] Launch the Project — development tasks created; interactive launch is user-controlled
- [x] Ensure Documentation is Complete

## Development rules

- Keep the frontend in React with JavaScript and Vite.
- Keep the backend in Python with FastAPI and SQLAlchemy.
- Preserve the pluggable Google Document AI provider and safe local mock mode.
- Never commit cloud credentials, uploaded documents, local databases, or `.env` files.
- Keep Czech user-facing text and accessible responsive styling.
- Keep the full dashboard owner-only for Vratislav; employees may only upload documents and view their own date-filtered statement.
- Run the `DokladFlow: ověřit projekt` task after relevant changes.
- Keep README.md current when setup, integrations, or API behavior changes.
