import "./globals.css";
import type { ReactNode } from "react";
import Providers from "../components/Providers";
import AppShell from "../components/AppShell";
export const metadata = {
  title: "LifeStory — AI Biographer",
  description: "Preserve memories and create a biographical film.",
};
export default function Layout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
