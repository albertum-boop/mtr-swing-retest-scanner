const fs = require("fs");

const THREAD_TITLE = "MTR · informes automáticos de señales";

module.exports = async ({ github, context, core }, reportPath) => {
  const body = fs.readFileSync(reportPath, "utf8").trim();
  if (!body) {
    core.info("No hay señales nuevas; no se publica alerta diaria.");
    return;
  }

  const marker = body.match(/^<!-- mtr-report:[^>]+ -->/)?.[0];
  if (!marker) {
    throw new Error("El informe no contiene un identificador de idempotencia válido");
  }

  const { owner, repo } = context.repo;
  const issues = await github.paginate(github.rest.issues.listForRepo, {
    owner,
    repo,
    state: "all",
    per_page: 100,
  });
  let thread = issues.find(
    (issue) => !issue.pull_request && issue.title === THREAD_TITLE,
  );

  if (!thread) {
    const created = await github.rest.issues.create({
      owner,
      repo,
      title: THREAD_TITLE,
      assignees: [owner],
      body:
        `@${owner}\n\nEste hilo recibe las alertas inmediatas y los resúmenes ` +
        "semanales del modelo MTR. GitHub enviará una notificación por cada informe.",
    });
    thread = created.data;
  }

  const comments = await github.paginate(github.rest.issues.listComments, {
    owner,
    repo,
    issue_number: thread.number,
    per_page: 100,
  });
  if (comments.some((comment) => String(comment.body || "").includes(marker))) {
    core.info(`Informe ${marker} ya publicado; se omite el duplicado.`);
    return;
  }

  await github.rest.issues.createComment({
    owner,
    repo,
    issue_number: thread.number,
    body: `@${owner}\n\n${body}`,
  });
  core.notice(`Informe publicado en #${thread.number}`);
};
