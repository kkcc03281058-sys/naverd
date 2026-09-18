/**
 * 통화 기록 -> 구글 시트 자동 저장 텔레그램 봇
 *
 * 동작 방식
 *  1) 텔레그램으로 전화번호를 텍스트로 보내면 -> 파싱해서 시트에 한 줄 기록
 *  2) 통화기록 캡처 사진을 보내면 -> OCR로 텍스트 추출 후 같은 방식으로 기록
 *
 * 사전 준비 (스크립트 속성에 등록, "프로젝트 설정 > 스크립트 속성")
 *   TELEGRAM_BOT_TOKEN : @BotFather 에서 발급받은 봇 토큰
 *   ALLOWED_CHAT_ID    : 본인 텔레그램 chat_id (미입력 시 아무나 봇에 기록 가능하므로 반드시 등록 권장)
 *   SHEET_NAME         : 기록할 시트 이름 (미입력 시 "통화기록")
 *
 * 사전 준비 (Apps Script 편집기)
 *   좌측 "서비스(+)" -> Drive API (고급 서비스) 추가  <- OCR에 필요
 *
 * 배포
 *   배포 > 새 배포 > 웹 앱, 실행: 나, 액세스 권한: 모든 사용자
 *   배포 후 나오는 웹앱 URL을 아래 주소로 한 번 접속해서 텔레그램 웹훅으로 등록
 *   https://api.telegram.org/bot<TOKEN>/setWebhook?url=<웹앱URL>
 */

var HEADER = ['날짜', '전화번호', '통화시작', '메모', '사진', '등록시각'];

function doPost(e) {
  var props = PropertiesService.getScriptProperties();
  var token = props.getProperty('TELEGRAM_BOT_TOKEN');
  var allowedChatId = props.getProperty('ALLOWED_CHAT_ID');

  var update = JSON.parse(e.postData.contents);
  var message = update.message;
  if (!message) return ContentService.createTextOutput('ok');

  var chatId = message.chat.id;
  if (allowedChatId && String(chatId) !== String(allowedChatId)) {
    return ContentService.createTextOutput('ok'); // 허용되지 않은 사용자는 무시
  }

  try {
    var record = message.photo
      ? buildRecordFromPhoto(message, token)
      : buildRecordFromText(message);

    appendRecord(record);
    replyTelegram(token, chatId,
      '✅ 기록 완료\n날짜: ' + record.date +
      '\n전화번호: ' + (record.phone || '(인식 실패, 시트에서 직접 수정해주세요)') +
      '\n통화시작: ' + record.callTime +
      '\n메모: ' + (record.memo || '-'));
  } catch (err) {
    replyTelegram(token, chatId, '⚠️ 기록 실패: ' + err.message);
  }

  return ContentService.createTextOutput('ok');
}

function buildRecordFromText(message) {
  var text = message.text || message.caption || '';
  var parsed = parseCallInfo(text, message.date);
  parsed.photoUrl = '';
  return parsed;
}

function buildRecordFromPhoto(message, token) {
  var photos = message.photo;
  var fileId = photos[photos.length - 1].file_id; // 마지막 원소가 최고 해상도
  var blob = downloadTelegramFile(token, fileId);
  var ocrText = ocrImage(blob);
  var captionText = message.caption || '';
  var parsed = parseCallInfo(ocrText + '\n' + captionText, message.date);

  var driveFile = DriveApp.createFile(blob).setName('call_' + new Date().getTime());
  parsed.photoUrl = driveFile.getUrl();
  return parsed;
}

function parseCallInfo(rawText, telegramDateSec) {
  var text = rawText || '';
  var tz = 'Asia/Seoul';
  var now = telegramDateSec ? new Date(telegramDateSec * 1000) : new Date();

  var phoneMatch = text.match(/01[016789]-?\d{3,4}-?\d{4}/);
  var phone = phoneMatch ? phoneMatch[0].replace(/-/g, '') : '';
  phone = phone ? phone.replace(/(\d{3})(\d{3,4})(\d{4})/, '$1-$2-$3') : '';

  var dateMatch = text.match(/(\d{4})[.\-\/](\d{1,2})[.\-\/](\d{1,2})/);
  var dateStr = dateMatch
    ? dateMatch[1] + '-' + ('0' + dateMatch[2]).slice(-2) + '-' + ('0' + dateMatch[3]).slice(-2)
    : Utilities.formatDate(now, tz, 'yyyy-MM-dd');

  var timeMatch = text.match(/(\d{1,2})[:시](\d{2})/);
  var callTime = timeMatch
    ? ('0' + timeMatch[1]).slice(-2) + ':' + timeMatch[2]
    : Utilities.formatDate(now, tz, 'HH:mm');

  var memo = text
    .replace(phoneMatch ? phoneMatch[0] : '', '')
    .replace(dateMatch ? dateMatch[0] : '', '')
    .replace(timeMatch ? timeMatch[0] : '', '')
    .replace(/\s+/g, ' ')
    .trim();

  return { date: dateStr, phone: phone, callTime: callTime, memo: memo };
}

function appendRecord(record) {
  var props = PropertiesService.getScriptProperties();
  var sheetName = props.getProperty('SHEET_NAME') || '통화기록';
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(sheetName);
  if (!sheet) {
    sheet = ss.insertSheet(sheetName);
    sheet.appendRow(HEADER);
  }
  sheet.appendRow([
    record.date,
    record.phone,
    record.callTime,
    record.memo,
    record.photoUrl || '',
    Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss')
  ]);
}

function downloadTelegramFile(token, fileId) {
  var fileInfoUrl = 'https://api.telegram.org/bot' + token + '/getFile?file_id=' + fileId;
  var fileInfo = JSON.parse(UrlFetchApp.fetch(fileInfoUrl).getContentText());
  var filePath = fileInfo.result.file_path;
  var fileUrl = 'https://api.telegram.org/file/bot' + token + '/' + filePath;
  return UrlFetchApp.fetch(fileUrl).getBlob();
}

function ocrImage(blob) {
  // Drive 고급 서비스(Drive API v2)를 이용한 무료 OCR
  var resource = {
    title: 'ocr_temp_' + new Date().getTime(),
    mimeType: blob.getContentType()
  };
  var ocrFile = Drive.Files.insert(resource, blob, { ocr: true, ocrLanguage: 'ko' });
  var doc = DocumentApp.openById(ocrFile.id);
  var text = doc.getBody().getText();
  Drive.Files.remove(ocrFile.id); // 임시 OCR 문서 삭제 (원본 캡처 사진은 별도로 남아있음)
  return text;
}

function replyTelegram(token, chatId, text) {
  UrlFetchApp.fetch('https://api.telegram.org/bot' + token + '/sendMessage', {
    method: 'post',
    payload: { chat_id: chatId, text: text }
  });
}
