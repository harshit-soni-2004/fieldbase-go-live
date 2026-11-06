import json
import secrets
from dataclasses import dataclass
from typing import Any, Optional, Protocol
from app.agent.http_tools import HttpToolsClient

@dataclass
class StepRecord:
    step_index: int
    tool_name: str
    http_status: int
    error_code: Optional[str]
    replayed: bool
    arguments: dict[str, Any]

@dataclass
class AgentRunResult:
    run_id: str
    stopped_reason: str
    final_text: str
    steps: list[StepRecord]

class RunRecorder(Protocol):
    def on_run_start(
        self,
        run_id: str,
        scenario: str,
        contract_id: str,
        mode: str,
        idempotency_key: str,
    ) -> None:
        ...

    def on_step_complete(
        self,
        run_id: str,
        step_index: int,
        tool_name: str,
        arguments_json: str,
        http_status: int,
        error_code: Optional[str],
        result_json: str,
    ) -> None:
        ...

    def on_run_finish(
        self,
        run_id: str,
        stopped_reason: str,
        final_text: str,
    ) -> None:
        ...

def run_agent_loop(
    scenario: str,
    contract_id: str,
    idempotency_key: str,
    mode: str,
    base_url: str,
    agent_token: str,
    model: Any,
    recorder: Optional[RunRecorder] = None,
    run_id: Optional[str] = None,
) -> AgentRunResult:
    if not run_id:
        run_id = f"run_{secrets.token_hex(6)}"

    # 1. Insert a runs row
    if recorder:
        recorder.on_run_start(
            run_id=run_id,
            scenario=scenario,
            contract_id=contract_id,
            mode=mode,
            idempotency_key=idempotency_key,
        )

    http_client = HttpToolsClient(base_url=base_url, agent_token=agent_token)
    steps: list[StepRecord] = []
    stopped_reason = "model_stop"
    final_text = ""
    step_count = 0

    try:
        while step_count < 12:
            # 2. Ask the model for one tool call
            action = model.next_action()

            if action.get("stop", False):
                stopped_reason = "model_stop"
                final_text = action.get("final_text", "")
                break

            step_count += 1
            tool_name = action.get("tool", "")
            arguments = action.get("arguments", {})

            # 3. Perform that call over HTTP with the agent token and X-Run-Id
            exec_result = http_client.execute_tool(
                tool_name=tool_name,
                arguments=arguments,
                idempotency_key=idempotency_key,
                run_id=run_id,
            )

            # 4. Insert a run_steps row using the real HTTP status and body
            args_json_str = json.dumps(exec_result.sent_arguments)
            res_json_str = json.dumps(exec_result.body) if not isinstance(exec_result.body, str) else exec_result.body

            if recorder:
                recorder.on_step_complete(
                    run_id=run_id,
                    step_index=step_count,
                    tool_name=tool_name,
                    arguments_json=args_json_str,
                    http_status=exec_result.http_status,
                    error_code=exec_result.error_code,
                    result_json=res_json_str,
                )

            step_record = StepRecord(
                step_index=step_count,
                tool_name=tool_name,
                http_status=exec_result.http_status,
                error_code=exec_result.error_code,
                replayed=exec_result.replayed,
                arguments=exec_result.sent_arguments,
            )
            steps.append(step_record)

            # 5. Return that result to the model
            if hasattr(model, "receive_result"):
                model.receive_result(tool_name, exec_result.body)

            if step_count >= 12:
                stopped_reason = "step_limit"
                break

    finally:
        http_client.close()
        # 6. Finalize run
        if recorder:
            recorder.on_run_finish(
                run_id=run_id,
                stopped_reason=stopped_reason,
                final_text=final_text,
            )

    return AgentRunResult(
        run_id=run_id,
        stopped_reason=stopped_reason,
        final_text=final_text,
        steps=steps,
    )
