"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

// Sends visitors from the home address to the sign-in page.
export default function Home() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/login");
  }, [router]);

  return null;
}
