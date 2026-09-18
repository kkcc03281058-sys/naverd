/**
 * 통화 기록 -> 구글 시트 자동 저장 텔레그램 봇 (폴링 방식)
 *
 * 동작 방식
 *  - 1분마다(시간 기반 트리거) 텔레그램에 새 메시지가 있는지 직접 확인(getUpdates)
 *  - 전화번호를 텍스트로 보내면 -> 파싱해서 시트에 한 줄 기록
 *  - 통화기록 캡처 사진을 보내면 -> OCR로 텍스트 추출 후 같은 방식으로 기록
 *
 * 웹훅(doPost) 대신 폴링을 쓰는 이유
 *  Apps Script 웹앱은 응답 시 내부적으로 302 리다이렉트를 거치는데,
 *  텔레그램의 웹훅 전송기는 리다이렉트를 따라가지 않아 계속 실패로 처리한다.
 *  반대로 우리가 텔레그램에 직접 요청을 보내는 방식(getUpdates/sendMessage)은
 *  이 문제가 없으므로 폴링 방식을 사용한다.
 *
 * 사전 준비 (스크립트 속성에 등록, "프로젝트 설정 > 스크립트 속성")
 *   TELEGRAM_BOT_TOKEN : @BotFather 에서 발급받은 봇 토큰
 *   ALLOWED_CHAT_ID    : 허용할 텔레그램 chat_id (여러 명이면 콤마로 구분, 예: "111,222,333")
 *                        (미입력 시 아무나 봇에 기록 가능하므로 반드시 등록 권장)
 *   SHEET_NAME         : 기록할 시트 이름 (미입력 시 "통화기록")
 *
 * 사전 준비 (Apps Script 편집기)
 *   좌측 "서비스(+)" -> Drive API (고급 서비스) 추가  <- OCR에 필요
 *
 * 트리거 설정 (필수)
 *   좌측 시계 모양 "트리거" 메뉴 -> 우측 하단 "트리거 추가"
 *   -> 실행할 함수: checkTelegramUpdates
 *   -> 이벤트 소스: 시간 기반 트리거
 *   -> 시간 기반 트리거 유형: 분 단위 타이머
 *   -> 시간 간격: 1분마다
 *   -> 저장
 */

var HEADER = ['날짜', '전화번호', '통화시작', '메모', '사진', '등록시각'];

function getAllowedChatIds(props) {
  var raw = props.getProperty('ALLOWED_CHAT_ID') || '';
  return raw.split(',')
    .map(function (id) { return id.trim(); })
    .filter(function (id) { return id.length > 0; });
}

function checkTelegramUpdates() {
  var props = PropertiesService.getScriptProperties();
  var token = props.getProperty('TELEGRAM_BOT_TOKEN');
  var lastUpdateId = Number(props.getProperty('LAST_UPDATE_ID') || '0');

  var url = 'https://api.telegram.org/bot' + token + '/getUpdates'
    + '?offset=' + (lastUpdateId + 1) + '&timeout=0';
  var response = UrlFetchApp.fetch(url, { muteHttpExceptions: true });

  if (response.getResponseCode() !== 200) {
    logError(new Error('getUpdates 실패: ' + response.getContentText()), null);
    return;
  }

  var data = JSON.parse(response.getContentText());
  if (!data.ok || !data.result || data.result.length === 0) return;

  var allowedChatIds = getAllowedChatIds(props);
  var maxUpdateId = lastUpdateId;

  data.result.forEach(function (update) {
    if (update.update_id > maxUpdateId) maxUpdateId = update.update_id;
    processUpdate(update, token, allowedChatIds);
  });

  props.setProperty('LAST_UPDATE_ID', String(maxUpdateId));
}

function processUpdate(update, token, allowedChatIds) {
  var message = update.message;
  if (!message) return;

  var chatId = message.chat.id;
  if (allowedChatIds.length > 0 && allowedChatIds.indexOf(String(chatId)) === -1) {
    return; // 허용되지 않은 사용자는 무시
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
    logError(err, { postData: { contents: JSON.stringify(update) } });
    try {
      replyTelegram(token, chatId, '⚠️ 기록 실패: ' + err.message);
    } catch (err2) {
      // 텔레그램 응답 전송도 실패하면 에러로그 시트만 남긴다
    }
  }
}

function logError(err, e) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName('에러로그');
  if (!sheet) {
    sheet = ss.insertSheet('에러로그');
    sheet.appendRow(['시각', '에러 메시지', '스택', '원본 요청']);
  }
  sheet.appendRow([
    Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss'),
    err && err.message,
    err && err.stack,
    e && e.postData ? e.postData.contents : ''
  ]);
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
  var url = 'https://api.telegram.org/bot' + token + '/sendMessage'
    + '?chat_id=' + encodeURIComponent(chatId)
    + '&text=' + encodeURIComponent(text);
  var response = UrlFetchApp.fetch(url, { muteHttpExceptions: true });
  if (response.getResponseCode() !== 200) {
    logError(new Error('sendMessage 실패: ' + response.getContentText()), null);
  }
}
