import { useRouter } from 'next/router';
import TaskGraphEditor from '../../../components/TaskGraphEditor';

export default function EditPage() {
  const router = useRouter();
  const { execution_plan_id } = router.query as { execution_plan_id: string };
  if (!execution_plan_id) return null;
  return <TaskGraphEditor executionPlanId={execution_plan_id} />;
}
