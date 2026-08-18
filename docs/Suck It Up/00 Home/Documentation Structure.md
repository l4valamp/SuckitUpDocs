
- [[Features]]
	- Part of the game that needs its own documentation. yeah, that's kind of it, u,m. yeah, um.. um yeah, um...
	- Sub-features
	- Feature Breakdowns
	- Each feature has own landing page/All Related Docs. (Technical docs, Design docs, for design docs). 
- [[Technical Breakdown]] 
	- Tech document for a given feature or system
- [[Needs]]
	- Individual items that need completed
	- Status (completed percent)
	- Team
- [[Tasks]]
	- Sprint-like tasks that could have group of needs.
	- Story points
	- status
	- Assigned to
	- Once a task is approved, all needs should be marked completed

- If TASKS are COMPLETED the NEED is marked as done. 
- Needs shown on:
	- Feature Page
	- Task Page
	- Team Page
- When Needs are completed, they are removed from the TEAM page. They are sorted to the bottom on TASK and FEATURE pages. 

- TO-DO:
- Needs on team pages


``` mermaid
flowchart TD
  A[Categories] --> |Display all features tagged with this category| B[Features];
  B --> C[Sub-Features];
  C --> D[Needs];
  B --> D;
  E[Tasks] -->|Each task contains one or several Needs. If a need has been assigned to a task, it will inherit that Task's completion status.| D;
  F[Sprints] --> |Sprints are a collection of Tasks| E;
```

TODO:
If tasks are complete, move them to the bottom or remove them from the page
