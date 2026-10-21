"""Render existing scoring output for an applicant; no network or new LLM calls."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit


def plain(value):
    return str(value or "").replace("\r", " ").replace("\n", " ").replace("[", "\\[").replace("]", "\\]")


def render(payload, limit=10):
    rows = payload.get("vacancies", [])
    if not isinstance(rows, list) or not rows:
        raise ValueError("Нет оценённых вакансий: проверь завершение анализа и сообщения о модели/API.")
    lines = ["# Вакансии для откликов", "", f"Дата анализа: {plain(payload.get('last_updated', 'не указана'))}", "",
             "Баллы — модельные оценки, а не вероятность найма. Приоритет следует карьерному направлению; обязательные пробелы и актуальность вакансии проверь перед откликом."]
    for index, row in enumerate(rows[:limit], 1):
        title = f"{plain(row.get('company'))}: {plain(row.get('title'))}"
        url = str(row.get('link', ''))
        safe_url = url.replace('(', '%28').replace(')', '%29').replace(' ', '%20')
        linked = f"[{title}]({safe_url})" if urlsplit(url).scheme == 'https' and '\n' not in url else title
        goal = row.get('career_goal_alignment')
        lines += ["", f"## {index}. {linked}", "",
                  f"Готовность по CV: {row.get('ats_score', 'не рассчитана')}/100. Соответствие карьерной цели: {str(goal) + '/100' if goal is not None else 'не оценено — требуется отдельная проверка'}.", "",
                  f"Решение: {plain(row.get('application_recommendation')) or 'Проверь требования и объяснение; автоматическая рекомендация отсутствует.'}", "",
                  plain(row.get('reasoning')), "", "Подтверждённые совпадения: " + ', '.join(plain(x) for x in row.get('matched_keywords', [])), "",
                  "Не подтверждено резюме: " + ', '.join(plain(x) for x in row.get('missing_keywords', []))]
        tips = row.get('improvement_tips', [])
        if tips: lines += ["", "Что изменить в резюме:", ""] + [f"- {plain(tip)}" for tip in tips]
        if row.get('application_message'): lines += ["", "Черновик отклика (сверить факты перед отправкой):", "", str(row['application_message'])]
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--limit', type=int, default=10)
    args = parser.parse_args()
    if args.limit < 1: parser.error('--limit должен быть положительным')
    try:
        result = render(json.loads(Path(args.input).read_text(encoding='utf-8')), args.limit)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.error(str(exc))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result, encoding='utf-8')
    print(f'Отчёт: {output.resolve()}')


if __name__ == '__main__': main()
