import logging
from typing import List
from .execution_task_graph_management import ExecutionTaskGraph

logger = logging.getLogger(__name__)

async def build_context_summary(task_id: str, execution_plan_id: str, max_depth: int = 3) -> str:
    """Build a short textual summary of the context of a task.

    Args:
        task_id: Identifier of the task for which to build context.
        execution_plan_id: Identifier of the execution plan (ExecutionTaskGraph).
        max_depth: How many ancestor levels to include.
    Returns:
        A formatted string summarising parents and related artifacts.
    """
    prefix = "[CTX_BUILDER]"
    graph = ExecutionTaskGraph(execution_plan_id)
    task = graph.get_task(task_id)
    if not task:
        logger.warning(f"{prefix} task {task_id} not found in plan {execution_plan_id}")
        return ""

    lines: List[str] = [f"🎯 Objectif actuel : {task.objective}"]

    # Traverse parents
    parent_id = task.parent_id
    depth = 1
    while parent_id and depth <= max_depth:
        parent = graph.get_task(parent_id)
        if not parent:
            break
        lines.append(f"↪️ Parent (niveau {depth}) : {parent.objective}")
        if parent.result_summary:
            lines.append(f"📄 Résumé : {parent.result_summary}")
        parent_id = parent.parent_id
        depth += 1

    related: List[str] = []
    # Dependencies first
    for dep_id in task.dependencies:
        if len(related) >= 3:
            break
        dep = graph.get_task(dep_id)
        if dep and dep.result_summary:
            related.append(f"• [{dep.id}] {dep.result_summary}")
    # Siblings
    if len(related) < 3 and task.parent_id:
        parent = graph.get_task(task.parent_id)
        if parent:
            for sib_id in parent.sub_task_ids:
                if sib_id == task.id or len(related) >= 3:
                    continue
                sib = graph.get_task(sib_id)
                if sib and sib.result_summary:
                    related.append(f"• [{sib.id}] {sib.result_summary}")

    if related:
        lines.append("🧩 Artefacts connexes :")
        lines.extend(related)

    summary = "\n".join(lines)
    logger.debug(f"{prefix} summary built for {task_id}: {summary}")
    return summary
