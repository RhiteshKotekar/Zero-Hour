# Zero-Hour / SAMG — Complete Dashboard UI/UX Redesign

Act as a senior product designer, frontend architect, and visualization engineer. Your task is to redesign the existing Zero-Hour SAMG dashboard into a polished, professional, judge-friendly application.

This is a substantial UI/UX improvement, NOT a request to build a new application from scratch.

You have access to the existing repository. Study the current implementation, understand its architecture, data flow, components, and functionality before making changes.

## 1. Project Context

SAMG (Secure Adaptive Mission Governance) is an intelligent coordination and governance system for warehouse robot fleets.

The application simulates a warehouse containing:
- Storage racks and SKUs.
- Customer orders and picking tasks.
- Autonomous mobile robots.
- Picking, transportation, packing and dispatch operations.
- Multiple warehouse coordination topologies.
- Intelligent task allocation and route planning.
- Assurance mechanisms involving signed claims, witnesses and an Admission Control Point (ACP).
- Adaptive decision-making using LinUCB.

The dashboard demonstrates how SAMG coordinates warehouse operations, makes decisions, allocates tasks, and verifies robot actions.

The existing application already has a functional 3D warehouse simulation, simulation controls, metrics, mission information, topology information, security information, and detailed operational views.

**Preserve the underlying functionality and focus on dramatically improving how it is presented.**

## 2. Design Direction

Completely rethink the visual hierarchy.

The current dashboard is too cluttered. Almost every piece of information is permanently visible, resulting in tiny text, numerous cards, excessive borders, and too many competing visual elements.

We want a dashboard that feels like a professionally designed enterprise product.

### Visual identity

- Light mode ONLY.
- Clean white and very light neutral-grey backgrounds.
- Subtle shadows and carefully controlled borders.
- Generous spacing and consistent alignment.
- Modern typography with excellent readability.
- Restrained use of colour.
- Smooth, purposeful transitions and micro-interactions.
- Clear visual distinction between normal, active, warning, and critical states.

Suggested palette:
- Primary background: #F7F8FA
- Surface: #FFFFFF
- Primary text: #17212F
- Secondary text: #697586
- Primary accent: #2563EB
- Success: #16A36A
- Warning: #E99A24
- Critical: #DC4545
- Borders: #E7EAF0

You may refine this palette if necessary.

Avoid:
- Dark mode.
- Neon colours.
- Excessive gradients.
- Glassmorphism everywhere.
- Excessive rounded cards.
- Tiny uppercase labels everywhere.
- Unnecessary badges and decorative indicators.
- Generic AI-generated dashboard aesthetics.
- Making every section look like a separate floating card.

The result should feel intentional, refined, and production-ready.

## 3. New Dashboard Information Architecture

Redesign the dashboard around the following structure.

### A. Top Navigation

Keep the header minimal.

Include:
- SAMG branding and product name.
- Simulation status.
- Current scenario / mission identifier.
- Selected topology.
- Assurance/security status.
- Navigation to Compare and Replays.

Do not fill the header with unnecessary information.

Use compact status indicators and readable text.

### B. Simulation Controls

Create a clean, compact simulation toolbar.

Include:
- Play / Pause.
- Step.
- Reset.
- Playback speed.
- Timeline scrubber.
- Inject event control.
- Operations / Communications access.

These controls must continue working exactly as they do currently.

Avoid oversized controls or excessive button styling.

### C. Main Workspace — 3D Warehouse

This should be the visual centrepiece of the application.

Give the 3D warehouse the majority of the available screen space.

It should feel immersive and visually impressive without sacrificing usability.

Improve:
- Warehouse visibility.
- Camera positioning.
- Lighting and shadows.
- Robot visibility.
- Rack and SKU labels.
- Task route visualization.
- Picking and dispatch activity.
- Congestion visualization.
- Robot state indicators.

Reduce unnecessary labels and overlays.

Only display essential information by default.

Provide controls to toggle:
- Routes.
- Robot labels.
- SKU labels.
- Coordination graph.
- Congestion.
- Effects.
- Focus mode.

Clicking a robot should open a contextual information panel containing its current task, location, status, destination, and relevant execution information.

Clicking an order should highlight its associated tasks and robot routes.

Do not unnecessarily change the underlying 3D scene, simulation engine, or data model.

### D. Mission Overview — Right Sidebar

Replace the current crowded right-hand panel with a clean, structured mission overview.

By default, display:

1. Active missions.
2. Customer orders.
3. Fleet status.
4. Current coordination topology.

Use a compact tabbed interface or clearly separated sections.

For customer orders, display:
- Order ID.
- Priority.
- Progress.
- Current status.

Clicking an order should expand its details, including:
- Required SKUs.
- Associated tasks.
- Assigned robots.
- Task dependencies.
- Execution history.

For topology, show the currently selected topology and a simple visual explanation of how coordination is being performed.

Detailed topology information should be accessible through an expandable section.

### E. Performance Overview

The current dashboard displays too many metrics simultaneously.

Replace this with a clean KPI strip containing only the most important indicators:

- Order completion.
- Fleet utilization.
- Average task latency.
- Travel distance.
- Congestion delay.
- Failed tasks.

Each metric should have:
- A prominent readable value.
- A short descriptive label.
- An optional trend indicator where actual historical data is available.

Clicking any metric should open a detailed analytics drawer or expanded panel containing relevant charts, breakdowns, and supporting information.

Do not invent trends or historical data.

### F. Detailed Information Workspace

This is where all the information currently competing for attention should live.

Create a clean tabbed workspace below the main simulation.

Suggested tabs:

1. Overview
2. Task Allocation
3. Assurance & Security
4. Event Stream
5. Mission Pipeline
6. Provenance
7. Performance Analytics

Keep the default view minimal.

Only load or display detailed information when the corresponding tab is selected, wherever technically appropriate.

For example:

**Task Allocation**
- Task ID.
- Customer order.
- Assigned robot.
- Priority.
- Status.
- Planned route.
- Execution timeline.

**Assurance & Security**
- Agent claims.
- Digital signatures.
- Witness verification.
- ACP admission decisions.
- Security violations.
- Learning eligibility.

**Event Stream**
- Chronological events.
- Robot activity.
- Task transitions.
- Verification results.
- System decisions.

**Mission Pipeline**
- Mission creation.
- Context extraction.
- Topology selection.
- Task allocation.
- Robot execution.
- Witness verification.
- ACP admission.

**Provenance**
- Decision history.
- Evidence references.
- Verification chain.
- Relevant timestamps.

Use appropriate tables, timelines, charts and expandable detail views.

Do not dump every available data point onto the screen at once.

## 4. Important: Make the Application Easy to Understand

Our primary audience includes hackathon judges who may not understand warehouse optimization, graph theory, reinforcement learning, or security protocols.

The dashboard should communicate what the system is doing without requiring technical knowledge.

Use clear labels.

For example:
- "Robot Utilization" rather than unexplained abbreviations.
- "Verified Actions" rather than cryptic security terminology.
- "Selected Coordination Strategy" rather than exposing implementation terminology everywhere.
- "Average Time per Task" rather than ambiguous latency labels.

Technical details must still be available in the detailed views.

Provide helpful tooltips for technical terms.

The default dashboard should answer these questions immediately:

1. What is happening in the warehouse?
2. How many robots are operating?
3. How many orders are being processed?
4. How is the system coordinating the robots?
5. Are operations progressing successfully?
6. Is the system verifying robot actions securely?

## 5. Visual Storytelling

This application is also a hackathon demonstration.

Make it visually impressive when a judge watches the simulation.

Prioritize:
- Smooth robot movement.
- Clearly distinguishable robot states.
- Animated route highlights.
- Subtle task completion animations.
- Clear congestion visualization.
- Meaningful status transitions.
- Smooth panel transitions.

Avoid animations that distract from the simulation.

The warehouse should communicate the system's intelligence visually rather than relying entirely on text and tables.

## 6. Functional Requirements — Extremely Important

This is a redesign of an existing functional application.

Do NOT turn it into a static prototype.

Before implementation:

1. Inspect the entire frontend architecture.
2. Identify the existing components and their responsibilities.
3. Identify how simulation state is received and updated.
4. Understand the API integration and data contracts.
5. Identify existing interactions and their event handlers.

Preserve:
- Backend API integrations.
- Existing simulation functionality.
- Real-time or replay-driven updates.
- Robot movement and task execution.
- Topology selection.
- Task allocation.
- Mission selection.
- Assurance and security mechanisms.
- Event streams.
- Existing charts and analytics.
- Replay, pause, step, reset and speed controls.

Do not:
- Replace backend data with hardcoded values.
- Create fake metrics.
- Use randomly generated values to make the dashboard look active.
- Replace functional controls with decorative buttons.
- Remove existing features just because they are difficult to fit into the new design.
- Change algorithmic behaviour as part of a visual redesign.
- Break existing API contracts.
- Introduce unnecessary dependencies.

If a feature is not currently implemented, do not pretend that it is functional.

## 7. Implementation Strategy

Work in phases.

**Phase 1 — Audit**
- Inspect the current frontend.
- Identify components that can be reused.
- Identify components requiring redesign.
- Understand existing data dependencies.
- Provide a short implementation plan.

**Phase 2 — Design System**
- Establish consistent typography, spacing, colours, borders and component styles.
- Create reusable UI components.
- Ensure consistency across the application.

**Phase 3 — Main Dashboard**
- Redesign navigation.
- Redesign simulation controls.
- Improve the 3D warehouse workspace.
- Implement the new mission overview sidebar.
- Redesign the KPI strip.

**Phase 4 — Detailed Views**
- Implement the tabbed information workspace.
- Add expandable details and contextual panels.
- Preserve all existing functionality.

**Phase 5 — Polish**
- Improve transitions and micro-interactions.
- Fix spacing, alignment and responsiveness.
- Check readability at different screen sizes.
- Remove unnecessary visual clutter.

**Phase 6 — Validation**
- Run the application.
- Check for frontend errors.
- Test every major interaction.
- Verify that data still comes from the existing backend.
- Verify that simulation controls work.
- Check that no existing feature has silently disappeared.

## 8. Acceptance Criteria

The redesign is successful only if:

1. The dashboard looks significantly cleaner and more professional.
2. The 3D warehouse is the main visual focus.
3. The default view communicates the system's state within seconds.
4. Advanced information remains accessible without cluttering the default view.
5. All existing functionality is preserved.
6. No fabricated or hardcoded operational metrics are introduced.
7. Judges can understand the system without understanding its underlying algorithms.
8. The application remains responsive and usable.
9. Existing tests pass, and new functionality is tested where necessary.

## Final Instruction

Do not make superficial CSS changes and call the redesign complete.

Think like a senior product designer redesigning an enterprise-grade robotics operations platform.

Prioritize information hierarchy, clarity, usability, visual storytelling, and functional integrity.

You have creative freedom over the layout and presentation, but not over the underlying system behaviour.

Make the dashboard feel like a polished product that could genuinely be used to monitor and coordinate a real warehouse robot fleet.

Start by inspecting the repository and then implement the redesign directly. Do not stop after producing mockups or a design proposal.