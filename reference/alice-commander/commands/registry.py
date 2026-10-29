"""The complete, fixed command surface; no speech or argv is executed."""
ROWS = [
('terminal.open','открой терминал','Система'),('browser.open','открой браузер','Система'),
('desktop.lock','заблокируй компьютер','Система'),('desktop.show','покажи рабочий стол','Система'),('workspace.next','переключи рабочее пространство','Система'),
('volume.up','прибавь звук компьютера','Медиа'),('volume.down','убавь звук компьютера','Медиа'),('volume.mute','выключи звук компьютера','Медиа'),('media.pause','поставь музыку на паузу на компьютере','Медиа'),('media.next','следующий трек на компьютере','Медиа'),
('editor.open','открой VS Code','Разработка'),('project.open','открой проект','Разработка'),('github.open','открой GitHub','Разработка'),('project.test','запусти тесты проекта','Разработка'),('git.status','покажи статус Git','Разработка'),
('system.health','как чувствует себя компьютер','Мониторинг'),('system.memory','сколько свободной памяти','Мониторинг'),('system.temperature','какая температура процессора','Мониторинг'),('network.check','работает ли интернет','Мониторинг'),('build.status','как там моя сборка','Мониторинг'),
('rgb.rainbow','включи радугу','RGB'),('rgb.purple','включи фиолетовую подсветку','RGB'),('rgb.brighter','сделай подсветку ярче','RGB'),('rgb.night','включи ночной режим','RGB'),('rgb.off','выключи декоративную подсветку','RGB'),
('mode.work','включи компьютерный рабочий режим','Режимы'),('mode.rest','включи компьютерный режим отдыха','Режимы'),('mode.study','подготовь компьютер к учёбе','Режимы'),('mode.away','я отошёл','Режимы'),('mode.back','я вернулся','Режимы')]
from integrations.phone.phone_commands import ROWS as PHONE_ROWS
ROWS += [(cid,phrase,'Phone Control') for cid,phrase,_ in PHONE_ROWS]
COMMANDS={cid:{'id':cid,'phrase':'Алиса, '+phrase,'group':group} for cid,phrase,group in ROWS}
