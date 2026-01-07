import type { Metadata } from "next";
import Providers from "./providers";

export const metadata: Metadata = {
  title: "テナントAIアシスタント",
  description: "テナント入居者向けAIアシスタント＆FAQ検索システム（MVP）",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ja">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
