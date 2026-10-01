import type { Metadata } from "next";
import { Dela_Gothic_One, JetBrains_Mono, Zen_Kaku_Gothic_New } from "next/font/google";
import { AppHeader } from "@/components/AppHeader";
import { JobsProvider } from "@/components/jobs/JobsProvider";
import { JobTray } from "@/components/jobs/JobTray";
import "./globals.css";

const dela = Dela_Gothic_One({ variable: "--font-dela", weight: "400", subsets: ["latin"] });
const zen = Zen_Kaku_Gothic_New({ variable: "--font-zen", weight: ["400", "500", "700"], subsets: ["latin"] });
const jetbrains = JetBrains_Mono({ variable: "--font-jetbrains", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Anime Remix Studio",
  description: "Pull dialogue out of anime scenes and remix it over music.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${dela.variable} ${zen.variable} ${jetbrains.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col">
        <JobsProvider>
          <AppHeader />
          <main className="flex-1 w-full max-w-7xl mx-auto px-4 sm:px-6 pb-28 pt-6">{children}</main>
          <JobTray />
        </JobsProvider>
      </body>
    </html>
  );
}
