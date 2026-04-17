import { getInitials, resolveAssetUrl } from "@/shared/lib/userProfile";

interface Props {
  className?: string;
  imageClassName?: string;
  imageUrl?: string | null;
  name: string;
}

export function Avatar({
  className = "h-10 w-10",
  imageClassName = "",
  imageUrl,
  name,
}: Props) {
  const resolvedImageUrl = resolveAssetUrl(imageUrl);

  if (resolvedImageUrl) {
    return (
      <img
        alt={name}
        className={`rounded-full border border-black/10 bg-white object-cover ${className} ${imageClassName}`.trim()}
        src={resolvedImageUrl}
      />
    );
  }

  return (
    <div
      aria-hidden="true"
      className={`flex items-center justify-center rounded-full border border-black/10 bg-ember/10 font-bold uppercase text-ember ${className}`.trim()}
    >
      {getInitials(name)}
    </div>
  );
}
