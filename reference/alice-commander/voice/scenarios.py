"""Fixed scenario-name -> existing command ID allowlist. No free text execution."""
TEST_SCENARIO='Компьютерный режим'
ROWS=[
('Компьютер Терминал','terminal.open'),('Компьютер Браузер','browser.open'),
('Компьютер Блокировка','desktop.lock'),('Компьютер Рабочий стол','desktop.show'),('Компьютер Следующее пространство','workspace.next'),
('Компьютер Громче','volume.up'),('Компьютер Тише','volume.down'),('Компьютер Без звука','volume.mute'),('Компьютер Пауза','media.pause'),('Компьютер Следующий трек','media.next'),
('Компьютер Редактор','editor.open'),('Компьютер Проект','project.open'),('Компьютер GitHub','github.open'),('Компьютер Тесты','project.test'),('Компьютер Статус Git','git.status'),
('Компьютер Состояние','system.health'),('Компьютер Память','system.memory'),('Компьютер Температура','system.temperature'),('Компьютер Интернет','network.check'),('Компьютер Сборка','build.status'),
('Компьютер Радуга','rgb.rainbow'),('Компьютер Фиолетовый','rgb.purple'),('Компьютер Ярче','rgb.brighter'),('Компьютер Ночь','rgb.night'),('Компьютер Выключить подсветку','rgb.off'),
('Компьютер Работа','mode.work'),('Компьютер Отдых','mode.rest'),('Компьютер Учёба','mode.study'),('Компьютер Ушёл','mode.away'),('Компьютер Вернулся','mode.back')]
from integrations.phone.phone_commands import ROWS as PHONE_ROWS
ROWS += [(name,cid) for cid,_,name in PHONE_ROWS]
SCENARIOS={TEST_SCENARIO:'rgb.rainbow',**dict(ROWS)}
