# RiskLens AI Assistant — Architecture & Developer Guide

## 1. Why This Architecture Exists

The RiskLens AI Assistant provides personal analytics, financial reporting, and forecasting through a conversational interface. Rather than treating the LLM as a database or calculator, the architecture enforces strict boundaries between natural language reasoning and deterministic data calculation:

### Deterministic Computation vs. LLM Hallucination
LLMs are probabilistic token predictors; they are notoriously unreliable at arithmetic, time-series forecasting, and aggregation.
- **Tools compute everything**: All metrics, sums, confidence intervals, and time series are computed deterministically in Python (using Prophet, pandas, and SQLAlchemy).
- **The LLM never generates numbers**: The LLM's role is strictly limited to understanding user intent, calling the appropriate tools, and synthesizing friendly, concise prose.

### The Two-Channel Tool Result Design
When a tool executes, it produces a `ToolExecutionResult` with two distinct parts:
1. **`data` (to LLM)**: A compact summary (capped at 4 KB) containing high-level figures and status (e.g., `{"status": "ok", "total_predicted": 14500, "daily_avg": 483.33}`). This keeps LLM context usage low and response latency fast.
2. **`blocks` (to Client)**: Rich structured UI payloads (e.g. up to 120 rows of chart coordinates, upper/lower confidence bands, tone indicators) that are sent directly to the frontend. The LLM never sees or restates raw chart points.

### Security & Multi-Tenant Isolation
- **`user_id` from JWT only**: Tools never take `user_id` as an LLM argument. The authenticated `user_id` is extracted from the verified JWT on the server and passed via `ToolContext`. The LLM cannot access or query another user's data.
- **Prompt Injection Defense**: User notes, labels, and subcategories are treated strictly as data. User-controlled strings are sanitized (control characters stripped) and truncated before reaching the LLM or frontend.
- **Isolated DB Sessions**: Each tool creates its own short-lived session using `async_session()`. Concurrent tools run via `asyncio.gather` without sharing or corrupting database connection states.

### In-Memory Sliding-Window Rate Limiter
The assistant uses an in-memory sliding-window limiter (`ASSISTANT_RATE_LIMIT_PER_MIN = 20`) per user.
*Note: This limiter is per-process. In a horizontally scaled production deployment with multiple worker processes, this should be backed by an external store such as Redis.*

---

## 2. How to Add a New Tool

Follow these steps to add a new tool (for example, `get_study_summary`):

### Step 1: Define the Argument Schema
In `backend/app/services/assistant/tools.py`, create a Pydantic model for the arguments:
```python
class StudySummaryArgs(BaseModel):
    subject: Optional[str] = Field(default=None, description="Optional subject name")
    days: int = Field(default=7, ge=1, le=90, description="Past days to analyze")
```

### Step 2: Define the Tool Declaration
Declare the tool with a clear description that guides the Gemini router:
```python
STUDY_SUMMARY_DECLARATION = ToolDeclaration(
    name="get_study_summary",
    description="Summarize past study hours and focus sessions. Use for questions about study habits.",
    parameters=StudySummaryArgs.model_json_schema(),
)
```

### Step 3: Implement the Handler Function
Implement the async handler taking `(args, context: ToolContext) -> ToolExecutionResult`:
```python
async def execute_study_summary(
    args: StudySummaryArgs,
    context: ToolContext,
) -> ToolExecutionResult:
    async with async_session() as db:
        # Always filter by context.user_id and deleted_at IS NULL
        stmt = (
            select(Entry)
            .where(
                Entry.user_id == context.user_id,
                Entry.deleted_at.is_(None),
                Entry.category == "study",
            )
        )
        entries = (await db.execute(stmt)).scalars().all()

    total_hours = sum(float(e.value) for e in entries)
    
    # 1. Summary data for LLM
    data = {"status": "ok", "total_hours": total_hours, "sessions": len(entries)}
    
    # 2. UI blocks for client
    blocks = [
        build_metrics_block(
            title="Study Progress",
            items=[MetricItem(label="Total Hours", value=total_hours, format="number", tone="ok")]
        )
    ]
    return ToolExecutionResult(data=cap_data_payload(data), blocks=blocks)
```

### Step 4: Register in `TOOL_REGISTRY`
Add the tool to `TOOL_REGISTRY` in `backend/app/services/assistant/tools.py`:
```python
TOOL_REGISTRY["get_study_summary"] = RegisteredTool(
    name="get_study_summary",
    declaration=STUDY_SUMMARY_DECLARATION,
    args_model=StudySummaryArgs,
    handler=execute_study_summary,
)
```
The agent loop will automatically expose the declaration to Gemini, validate inputs, execute the tool concurrently, and forward the blocks to the client.

---

## 3. How to Add a New UI Block Type

Structured blocks are rendered inside the assistant message stream. To add a new block type (for example, `GoalCardBlock`):

### Backend:
1. **Define Schema**: In `backend/app/schemas/assistant.py`:
   ```python
   class GoalCardBlock(BaseModel):
       type: Literal["goal_card"] = "goal_card"
       id: str
       title: str
       target: float
       current: float
       deadline: Optional[str] = None
   ```
   Add `GoalCardBlock` to the `Block` union:
   ```python
   Block = Annotated[
       Union[MetricsBlock, ChartBlock, NoticeBlock, GoalCardBlock],
       Field(discriminator="type")
   ]
   ```
2. **Add Builder Function**: In `backend/app/services/assistant/blocks.py`:
   ```python
   def build_goal_card_block(title: str, target: float, current: float, block_id: Optional[str] = None) -> GoalCardBlock:
       return GoalCardBlock(id=block_id or make_block_id("goal"), title=title, target=target, current=current)
   ```

### Frontend:
1. **Define TypeScript Interface**: In `src/lib/assistantTypes.ts`:
   ```typescript
   export interface GoalCardBlock {
     type: "goal_card";
     id: string;
     title: string;
     target: number;
     current: number;
     deadline?: string | null;
   }
   ```
2. **Create React Component**: In `src/components/assistant/GoalCardBlock.tsx`:
   ```tsx
   export const GoalCardBlock: React.FC<{ block: GoalCardBlockType }> = ({ block }) => (
     <div className="p-3 bg-bg-soft border border-line rounded-lg">
       <h4>{block.title}</h4>
       <p>{block.current} / {block.target}</p>
     </div>
   );
   ```
3. **Register in `BLOCK_REGISTRY`**: In `src/components/assistant/BlockRenderer.tsx`:
   ```typescript
   const BLOCK_REGISTRY = {
     metrics: MetricsBlock,
     chart: ChartBlock,
     notice: NoticeBlock,
     goal_card: GoalCardBlock,
   };
   ```
*Extensibility Guarantee: If a client receives a block type it does not recognize, `BlockRenderer` returns `null` without crashing.*
