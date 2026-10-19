import { createHmac } from "node:crypto";
import { readFileSync } from "node:fs";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const API = process.env.AIA_E2E_API!;
const HOOK = process.env.AIA_E2E_HOOK!;
const JPEG_B64 = readFileSync("e2e/.gen/cam.jpg").toString("base64");

const OWNER = { email: "owner@demo.com", password: "owner-password-1" };
const VIEWER = { email: "viewer@demo.com", password: "viewer-password-1" };

let deviceToken = "";
let webhookSecret = "";
let cameraId = "";

const snap = async (page: Page, name: string) => {
  if (process.env.AIA_E2E_SHOTS) await page.screenshot({ path: `${process.env.AIA_E2E_SHOTS}/${name}.png`, fullPage: true });
};
const nav = (page: Page, name: string) => page.getByRole("navigation", { name: "Main" }).getByRole("link", { name, exact: true });

async function login(page: Page, who: { email: string; password: string }) {
  await page.goto("/");
  await page.getByLabel("Email").fill(who.email);
  await page.getByLabel("Password").fill(who.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible(); // wait until the session is really established
}
const logout = (page: Page) => page.getByRole("button", { name: "Sign out" }).click();

/** Plays the edge agent: the real one needs a camera, this speaks the same HTTP API. */
async function edge(request: APIRequestContext, method: "get" | "post", path: string, data?: object) {
  const res = await request[method](API + path, { headers: { Authorization: `Bearer ${deviceToken}` }, data });
  expect(res.ok(), `${path} -> ${res.status()}`).toBeTruthy();
  return res.status() === 204 ? null : res.json();
}
const uid = () => crypto.randomUUID();
const event = (kind: string, extra: object = {}) => ({ client_id: uid(), camera_id: cameraId, ts: new Date().toISOString(), kind, label: "person", track_id: 1, confidence: 0.9, data: {}, ...extra });

test.describe.serial("customer portal, end to end", () => {
  test("wrong password is rejected with a clear message", async ({ page }) => {
    await page.goto("/");
    await page.getByLabel("Email").fill("nobody@example.com");
    await page.getByLabel("Password").fill("wrong-password");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("alert")).toHaveText("Wrong email or password.");
  });

  test("superadmin creates a customer, sets retention and creates an edge device", async ({ page }) => {
    await login(page, { email: "root@example.com", password: "root-password-123" });
    await expect(page.getByRole("heading", { name: "Customers" })).toBeVisible();
    await expect(nav(page, "Dashboard")).toHaveCount(0); // platform admin sees no customer pages

    const form = page.getByRole("form", { name: "New customer" });
    await form.getByLabel("Company name").fill("Demo Store");
    await form.getByLabel("Owner email").fill(OWNER.email);
    await form.getByLabel("Owner password (10+ characters)").fill(OWNER.password);
    await form.getByRole("button", { name: "Create customer" }).click();
    const retention = page.getByLabel("Retention days for Demo Store");
    await expect(retention).toHaveValue("7"); // default retention
    await retention.fill("14");
    await retention.press("Tab");
    await page.reload();
    await expect(page.getByLabel("Retention days for Demo Store")).toHaveValue("14");

    await nav(page, "Edge devices").click();
    await page.getByLabel("Device name").fill("Office Mac mini");
    await page.getByRole("button", { name: "Create device" }).click();
    deviceToken = await page.locator(".secret code").innerText();
    expect(deviceToken).toMatch(/^aia_/);
    await expect(page.getByRole("cell", { name: "Office Mac mini" })).toBeVisible();
    await logout(page);
  });

  test("owner adds a camera and the edge machine supplies the preview picture", async ({ page, request }) => {
    await login(page, OWNER);
    await expect(page.getByRole("heading", { name: "No cameras yet" })).toBeVisible();
    await nav(page, "Cameras").click();
    await page.getByRole("button", { name: "Add camera" }).click();
    const form = page.getByRole("form", { name: "Add camera" });
    await form.getByLabel("New site name").fill("Main store");
    await form.getByLabel("Camera name").fill("Entrance");
    await form.getByLabel("Address (public IP or DDNS name)").fill("203.0.113.10");
    await form.getByLabel("Camera username").fill("admin");
    await form.getByLabel("Camera password").fill("s3cret/pw");
    await form.getByRole("button", { name: "Add camera" }).click();

    await expect(page.getByRole("heading", { name: "Entrance" })).toBeVisible();
    cameraId = page.url().split("/cameras/")[1].split("?")[0];
    await expect(page.getByRole("status").filter({ hasText: "Asking the edge machine" })).toBeVisible();

    // The edge agent polls, grabs a frame (here: a prepared JPEG) and answers.
    let req: { id: string; rtsp_url: string } | undefined;
    await expect.poll(async () => (req = (await edge(request, "get", "/edge/requests")).requests[0]), { timeout: 20_000 }).toBeTruthy();
    expect(req!.rtsp_url).toBe("rtsp://admin:s3cret%2Fpw@203.0.113.10:554/cam/realmonitor?channel=1&subtype=1");
    await edge(request, "post", `/edge/requests/${req!.id}`, { snapshot_b64: JPEG_B64 });

    const img = page.getByAltText("Camera preview");
    await expect(img).toBeVisible({ timeout: 15_000 });
    await expect.poll(() => img.evaluate((i: HTMLImageElement) => i.naturalWidth)).toBe(640);
  });

  test("draws a counting line and a zone, names them, saves and gets them back after reload", async ({ page, request }) => {
    await login(page, OWNER);
    await page.goto(`/cameras/${cameraId}`);
    const canvas = page.getByTestId("canvas");
    await expect(page.getByAltText("Camera preview")).toBeVisible();
    const box = (await canvas.boundingBox())!;
    const at = (fx: number, fy: number) => ({ x: box.width * fx, y: box.height * fy });

    await page.getByRole("button", { name: "Draw counting line" }).click();
    await canvas.click({ position: at(0.2, 0.5) });
    await canvas.click({ position: at(0.8, 0.5) });
    await page.getByLabel("Name of line1").fill("Door");

    await page.getByRole("button", { name: "Draw zone" }).click();
    for (const [x, y] of [[0.6, 0.15], [0.9, 0.15], [0.9, 0.4], [0.6, 0.4]]) await canvas.click({ position: at(x, y) });
    await canvas.click({ position: at(0.6, 0.15) }); // click the first corner again to close
    await page.getByLabel("Name of zone1").fill("Queue");
    await page.getByLabel("Dwell seconds for zone1").fill("10");

    await page.getByRole("button", { name: "Save changes" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Saved." })).toBeVisible();
    await page.reload();
    await snap(page, "camera-editor");
    await expect(page.getByLabel("Name of line1")).toHaveValue("Door");
    await expect(page.getByLabel("Name of zone1")).toHaveValue("Queue");
    await expect(page.getByLabel("Dwell seconds for zone1")).toHaveValue("10");

    // What the edge agent will receive: normalised coordinates, as drawn.
    const cfg = (await edge(request, "get", "/edge/config")).cameras.find((c: { id: string }) => c.id === cameraId);
    const line = cfg.analytics.lines[0];
    expect(line.name).toBe("Door");
    expect(line.p1[0]).toBeCloseTo(0.2, 1);
    expect(line.p1[1]).toBeCloseTo(0.5, 1);
    expect(line.p2[0]).toBeCloseTo(0.8, 1);
    expect(cfg.analytics.zones[0]).toMatchObject({ id: "zone1", name: "Queue", dwell_s: 10 });
    expect(cfg.analytics.zones[0].polygon).toHaveLength(4);
  });

  test("webhook + rule: only matching events notify, once, with a valid signature", async ({ page, request }) => {
    await login(page, OWNER);
    await nav(page, "Settings").click();
    await page.getByLabel("Webhook URL").fill(`${HOOK}/hook`);
    await page.getByRole("button", { name: "Save", exact: true }).click();
    webhookSecret = await page.locator(".secret code").innerText();
    expect(webhookSecret).toMatch(/^whsec_/);

    await nav(page, "Rules & alerts").click();
    await expect(page.getByRole("alert")).toHaveCount(0); // webhook is set, no warning
    const form = page.getByRole("form", { name: "New rule" });
    await form.getByLabel(/^Name/).fill("Customer came in");
    await form.getByLabel(/^Camera/).selectOption({ label: "Entrance" });
    await form.getByLabel(/^Line/).selectOption({ label: "Door" });
    await form.getByLabel(/^Direction/).selectOption({ label: "Coming IN" });
    await form.getByRole("button", { name: "Add rule" }).click();
    await expect(page.getByRole("cell", { name: "Customer came in", exact: true })).toBeVisible();
    await snap(page, "rules");

    const dir = (direction: string) => event("line_cross", { data: { line_id: "line1", direction } });
    const res = await edge(request, "post", "/edge/events", {
      events: [
        dir("out"), dir("in"), dir("in"), dir("in"),
        event("detection", { snapshot_b64: JPEG_B64 }),
        event("heatmap", { label: null, track_id: null, confidence: null, data: { grid: [32, 18], cells: { "300": 4, "301": 2 } } }),
      ],
    });
    expect(res).toEqual({ accepted: 6, rejected: 0 });

    const received = async () => (await (await request.get(`${HOOK}/received`)).json()) as { headers: Record<string, string>; body: string }[];
    await expect.poll(async () => (await received()).length, { timeout: 20_000 }).toBeGreaterThanOrEqual(1);
    await page.waitForTimeout(3000); // give any wrongly-extra deliveries time to show up
    const got = await received();
    expect(got).toHaveLength(1); // 'out' did not match; three 'in' collapse into one by the cooldown
    const { headers, body } = got[0];
    const lower = Object.fromEntries(Object.entries(headers).map(([k, v]) => [k.toLowerCase(), v]));
    const expected = "sha256=" + createHmac("sha256", webhookSecret).update(`${lower["x-aia-timestamp"]}.${body}`).digest("hex");
    expect(lower["x-aia-signature"]).toBe(expected);
    const payload = JSON.parse(body);
    expect(payload).toMatchObject({ type: "rule.triggered", rule: { name: "Customer came in" }, camera: { name: "Entrance" }, event: { kind: "line_cross", data: { direction: "in" } } });

    await nav(page, "Settings").click();
    await expect(page.locator(".pill.delivered").first()).toBeVisible();
  });

  test("dashboard shows visitor totals and heatmap; events page uses the names you gave", async ({ page }) => {
    await login(page, OWNER);
    await expect(page.getByTestId("total-in")).toHaveText("3");
    await expect(page.getByTestId("total-out")).toHaveText("1");
    await expect(page.getByTestId("heatmap").locator("rect")).toHaveCount(2);
    await snap(page, "dashboard");

    await nav(page, "Events").click();
    await expect(page.getByText('went in through "Door"')).toHaveCount(3);
    await expect(page.getByText('went out through "Door"')).toHaveCount(1);
    await snap(page, "events");
    await page.getByRole("row").filter({ hasText: "Detected" }).getByRole("button", { name: "Picture" }).click();
    const dialog = page.getByRole("dialog", { name: "Event snapshot" });
    const shot = dialog.getByAltText("Event snapshot");
    await expect(shot).toBeVisible();
    await expect.poll(() => shot.evaluate((i: HTMLImageElement) => i.naturalWidth)).toBe(640);
    await dialog.getByRole("button", { name: "Close" }).click();
    await expect(dialog).toHaveCount(0);
  });

  test("a viewer is read-only: no settings, rules or drawing tools", async ({ page }) => {
    await login(page, OWNER);
    await nav(page, "Settings").click();
    await page.getByLabel("New user email").fill(VIEWER.email);
    await page.getByLabel("New user password").fill(VIEWER.password);
    await page.getByRole("button", { name: "Add user" }).click();
    await expect(page.getByRole("cell", { name: VIEWER.email })).toBeVisible();
    await logout(page);

    await login(page, VIEWER);
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
    await expect(nav(page, "Settings")).toHaveCount(0);
    await expect(nav(page, "Rules & alerts")).toHaveCount(0);
    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible(); // redirected away
    await nav(page, "Cameras").click();
    await page.getByRole("link", { name: /Entrance/ }).click();
    await expect(page.getByRole("heading", { name: "Entrance" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Draw counting line" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Refresh picture" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Delete camera" })).toHaveCount(0);
  });

  test("works on a phone-sized screen without sideways scrolling", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 800 });
    await login(page, VIEWER);
    for (const path of ["/", "/cameras", `/cameras/${cameraId}`, "/events"]) {
      await page.goto(path);
      await expect(page.getByRole("heading").first()).toBeVisible();
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(overflow, `horizontal overflow on ${path}`).toBeLessThanOrEqual(1);
      if (path === "/") await snap(page, "dashboard-phone");
    }
  });

  test("an expired or invalid session returns to the login page", async ({ page }) => {
    await login(page, VIEWER);
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
    await page.evaluate(() => sessionStorage.setItem("aia_token", "garbage"));
    await page.reload();
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
  });
});
