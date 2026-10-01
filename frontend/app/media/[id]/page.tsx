import { ClipStudio } from "@/components/studio/ClipStudio";

export default async function MediaPage(props: PageProps<"/media/[id]">) {
  const { id } = await props.params;
  return <ClipStudio key={id} mediaId={id} />;
}
