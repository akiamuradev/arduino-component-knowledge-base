import { expect, test } from "@playwright/test";

const administrator = {
  id: "10000000-0000-4000-8000-000000000001",
  login: "administrator",
  display_name: "Integration Administrator",
  roles: ["administrator"],
};

test("an administrator signs in and reaches the protected dashboard", async ({ page }) => {
  let authenticated = false;
  let submittedLogin: string | undefined;

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/v1/auth/me") {
      await route.fulfill(
        authenticated
          ? { status: 200, contentType: "application/json", body: JSON.stringify(administrator) }
          : {
              status: 401,
              contentType: "application/json",
              body: JSON.stringify({ detail: { code: "authentication_required" } }),
            },
      );
      return;
    }
    if (path === "/api/v1/auth/login" && request.method() === "POST") {
      const payload = request.postDataJSON() as { login: string; password: string };
      submittedLogin = payload.login;
      authenticated = true;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ user: administrator, expires_at: "2026-07-17T12:00:00Z" }),
      });
      return;
    }
    if (path === "/api/v1/workspace/components") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [], total: 0 }),
      });
      return;
    }
    await route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ detail: { code: "unexpected_e2e_request", path } }),
    });
  });

  await page.goto("/admin");
  await expect(page).toHaveURL(/\/login$/);
  await page.getByLabel("Логин").fill("administrator");
  await page.getByLabel("Пароль").fill("local-test-passphrase");
  await page.getByRole("button", { name: "Войти" }).click();

  await expect(page).toHaveURL(/\/admin$/);
  await expect(page.getByRole("heading", { name: "Обзор материалов" })).toBeVisible();
  await expect(page.getByText("Карточек пока нет.")).toBeVisible();
  await expect(page.getByText("Права проверяются сервером")).toBeVisible();
  expect(submittedLogin).toBe("administrator");
});
