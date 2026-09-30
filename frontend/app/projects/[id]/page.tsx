import { TimelineEditor } from "@/components/timeline/TimelineEditor";

export default async function ProjectPage(props: PageProps<"/projects/[id]">) {
  const { id } = await props.params;
  return <TimelineEditor key={id} projectId={id} />;
}
