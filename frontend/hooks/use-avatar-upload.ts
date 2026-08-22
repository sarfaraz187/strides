"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import type { User } from "@/lib/auth-context";

const MAX_AVATAR_BYTES = 5 * 1024 * 1024;
const ALLOWED_AVATAR_TYPES = ["image/jpeg", "image/png"];

export type AvatarUploadError = "invalidType" | "tooLarge" | "uploadFailed";

export function useAvatarUpload() {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<AvatarUploadError | null>(null);

  const uploadAvatar = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append("file", file);
      const baseUrl = process.env.NEXT_PUBLIC_API_URL;
      const response = await fetch(`${baseUrl}/profile/avatar`, {
        method: "POST",
        credentials: "include",
        body: formData,
      });
      if (!response.ok) throw new Error("Upload failed");
      return (await response.json()) as { avatar_url: string };
    },
    onSuccess: ({ avatar_url }) => {
      setError(null);
      queryClient.setQueryData(["auth", "me"], (previous: User | null | undefined) => (previous ? { ...previous, avatar_url } : previous));
    },
    onError: () => setError("uploadFailed"),
  });

  function onFileChosen(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (!ALLOWED_AVATAR_TYPES.includes(file.type)) {
      setError("invalidType");
      return;
    }
    if (file.size > MAX_AVATAR_BYTES) {
      setError("tooLarge");
      return;
    }
    setError(null);
    uploadAvatar.mutate(file);
  }

  return {
    fileInputRef,
    error,
    isUploading: uploadAvatar.isPending,
    onFileChosen,
    triggerUpload: () => fileInputRef.current?.click(),
  };
}
