"""Render manual setup from the sole existing registry; never calls a cloud API."""
import json
from pathlib import Path
from commands.registry import COMMANDS
from voice.scenarios import ROWS
from voice.catalog import snapshot
ROOT=Path(__file__).resolve().parents[1]
def main():
    live={x['command_id']:x for x in snapshot(ROOT)}
    rows=[]
    for name,cid in ROWS:
        phrase=COMMANDS[cid]['phrase'].removeprefix('Алиса, ')
        rows.append({'scenario_name':name,'phrase':phrase,'alternative_phrase':'компьютер '+phrase,'command_id':cid,'action':{'device':'your Mini 1','instance':'text_action','value':'Ничего не делай'},'scenario_created':live[cid]['scenario_created'],'physically_confirmed':live[cid]['physical_confirmed'],'excluded_by_user':live[cid].get('excluded_by_user',False)})
    (ROOT/'config/voice-scenarios-export.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
    text='''# Настройка оставшихся сценариев V2

Эта таблица автоматически получена из существующей voice/scenarios.py и реестра
Commander. Новых идентификаторов нет. Ничего не отправляется в аккаунт Яндекса.

Для каждого ещё не созданного сценария:

1. «Дом с Алисой» → «+» → **Сценарий**.
2. Название скопировать из таблицы. Указать тот же дом/комнату, где стоит Mini.
3. «Если → Добавить условие → Фраза»: вписать фразу без слова «Алиса».
4. «Тогда → Добавить действие → ваша Станция Мини → Ответить на вопрос или
   выполнить команду»: **вручную написать «Ничего не делай»** в поле команды.
5. Сохранить действие, затем сохранить **весь сценарий** и выйти к списку карточек.
6. Через 30 секунд статус в Voice обновится; проверка действия может кэшироваться
   до двух минут. Создание карточки не является голосовым тестом.
7. Произнести «Алиса, <фраза>», проверить событие/результат в Voice и подтвердить
   реальный результат. Кнопка «Локальный тест» проверяет только действие на ПК.

Если фраза конфликтует с обычной Алисой, в условии можно использовать
«компьютер <фраза>» либо явно сказать «Алиса, запусти сценарий <название>».
UUID сопоставляется с существующим command_id; произвольный текст не исполняется.
Рабочий тестовый сценарий «Компьютерный режим» остаётся синонимом rgb.rainbow;
дополнительный «Компьютер Радуга» для покрытия 30 действий не обязателен.

Состояния таблицы — снимок на момент экспорта; живое состояние показывается в Voice.

| Название | Фраза | command_id | Создан | Физически проверен |
|---|---|---|---|---|
'''
    for x in rows:text+=f"| {x['scenario_name']} | {x['phrase']} | `{x['command_id']}` | {'Не требуется' if x['excluded_by_user'] else 'Да' if x['scenario_created'] else 'Нужно создать'} | {'Да' if x['physically_confirmed'] else 'Нет'} |\n"
    text+='\nИнформационные команды показывают результат в панели. Разблокировка голосом не предусмотрена. Следующий трек зависит от текущего MPRIS-плеера.\n'
    (ROOT/'VOICE_SETUP_V2.ru.md').write_text(text)
    print('Rendered 30 manual scenarios; no cloud writes.')
if __name__=='__main__':main()
