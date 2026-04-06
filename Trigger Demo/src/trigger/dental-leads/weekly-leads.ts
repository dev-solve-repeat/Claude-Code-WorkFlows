import { schedules } from "@trigger.dev/sdk";

// ── Types ────────────────────────────────────────────────────────────────────

interface SerperResult {
  title: string;
  link: string;
  snippet: string;
}

interface SerperResponse {
  organic?: SerperResult[];
}

interface Lead {
  name: string;
  city: string;
  sourceUrl: string;
  snippet: string;
  website: string;
  reason: string;
}

// ── Constants ────────────────────────────────────────────────────────────────

const INDIAN_CITIES = [
  "Mumbai",
  "Delhi",
  "Bangalore",
  "Chennai",
  "Hyderabad",
  "Pune",
  "Ahmedabad",
  "Kolkata",
  "Jaipur",
  "Surat",
];

const LEADS_TARGET = 10;

// Searches that surface dental practices likely to have no website
const SEARCH_TEMPLATES = [
  (city: string) => `dental clinic ${city} India site:justdial.com`,
  (city: string) => `dentist ${city} India site:practo.com`,
  (city: string) => `dental clinic ${city} India "no website"`,
];

// ── Serper helper ────────────────────────────────────────────────────────────

async function searchGoogle(query: string, apiKey: string): Promise<SerperResult[]> {
  const response = await fetch("https://google.serper.dev/search", {
    method: "POST",
    headers: {
      "X-API-KEY": apiKey,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ q: query, gl: "in", hl: "en", num: 10 }),
  });

  if (!response.ok) {
    console.error(`Serper error for "${query}": ${response.status}`);
    return [];
  }

  const data = (await response.json()) as SerperResponse;
  return data.organic ?? [];
}

function extractBusinessName(title: string): string {
  // Justdial/Practo titles look like "Dr. Smith Dental Clinic | Justdial"
  return title.split("|")[0].split("-")[0].trim();
}

// ── ClickUp helper ───────────────────────────────────────────────────────────

async function createClickUpTask(lead: Lead, token: string, listId: string): Promise<void> {
  const description = [
    `**City:** ${lead.city}, India`,
    `**Current Website:** ${lead.website}`,
    `**Why Prospect:** ${lead.reason}`,
    `**Source:** ${lead.sourceUrl}`,
    `**Snippet:** ${lead.snippet}`,
  ].join("\n");

  const response = await fetch(`https://api.clickup.com/api/v2/list/${listId}/task`, {
    method: "POST",
    headers: {
      Authorization: token,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      name: `${lead.name} — ${lead.city}`,
      description,
      priority: 3,
    }),
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(`ClickUp error ${response.status}: ${error}`);
  }
}

// ── Scheduled Task ───────────────────────────────────────────────────────────

export const weeklyDentalLeads = schedules.task({
  id: "weekly-dental-leads",
  cron: "30 3 * * 1", // Every Monday 9:00 AM IST (3:30 AM UTC)

  run: async () => {
    const serperApiKey = process.env.SERPER_API_KEY;
    if (!serperApiKey) throw new Error("SERPER_API_KEY is not set");

    const clickupToken = process.env.CLICKUP_API_TOKEN;
    if (!clickupToken) throw new Error("CLICKUP_API_TOKEN is not set");

    const clickupListId = process.env.CLICKUP_LIST_ID;
    if (!clickupListId) throw new Error("CLICKUP_LIST_ID is not set");

    const leads: Lead[] = [];
    const seenUrls = new Set<string>();

    for (const city of INDIAN_CITIES) {
      if (leads.length >= LEADS_TARGET) break;

      for (const buildQuery of SEARCH_TEMPLATES) {
        if (leads.length >= LEADS_TARGET) break;

        const query = buildQuery(city);
        console.log(`Searching: "${query}"`);
        const results = await searchGoogle(query, serperApiKey);

        for (const result of results) {
          if (leads.length >= LEADS_TARGET) break;
          if (seenUrls.has(result.link)) continue;

          seenUrls.add(result.link);

          const name = extractBusinessName(result.title);
          const isDirectory = /justdial|practo|sulekha|indianyellow/i.test(result.link);

          leads.push({
            name,
            city,
            sourceUrl: result.link,
            snippet: result.snippet,
            website: isDirectory ? "None (listed on directory only)" : result.link,
            reason: isDirectory
              ? "Only has a directory listing — no standalone website"
              : "Appears in search but may lack a professional website",
          });
        }
      }
    }

    console.log(`Found ${leads.length} leads. Posting to ClickUp...`);

    for (const lead of leads) {
      await createClickUpTask(lead, clickupToken, clickupListId);
      console.log(`✓ ${lead.name} — ${lead.city}`);
    }

    const summary = leads.map((l, i) => `${i + 1}. ${l.name} — ${l.city}`).join("\n");
    console.log(
      `\n✅ Dental Leads — Week of ${new Date().toDateString()}\nAdded ${leads.length} leads to ClickUp:\n${summary}`
    );

    return { leadsAdded: leads.length, leads };
  },
});
