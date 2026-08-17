import type { Metadata } from "next";
import { headers } from "next/headers";
import "./globals.css";

const title = "GreenFab Loop — 제조 자원순환 의사결정 MVP";
const description = "생산 위험 신호부터 자원 확인, AI 활용처 검색, 사람 승인, ESG Scenario, Green Receipt 초안까지 연결하는 근거 구분형 의사결정 서비스";

export async function generateMetadata(): Promise<Metadata> {
  const requestHeaders = await headers();
  const host = requestHeaders.get("x-forwarded-host") ?? requestHeaders.get("host") ?? "localhost:5173";
  const protocol = requestHeaders.get("x-forwarded-proto") ?? (host.includes("localhost") ? "http" : "https");
  const image = `${protocol}://${host}/og-enterprise.png`;

  return {
    title,
    description,
    icons: {
      icon: "/favicon.svg",
      shortcut: "/favicon.svg",
    },
    openGraph: {
      title,
      description,
      type: "website",
      locale: "ko_KR",
      images: [{ url: image, width: 1734, height: 907, alt: "GreenFab Loop — Detect, Match, Decide, Prove" }],
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
      images: [image],
    },
  };
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
