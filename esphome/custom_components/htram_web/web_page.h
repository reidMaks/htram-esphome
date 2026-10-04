#pragma once

namespace esphome {
namespace htram_web {

static const char STANDALONE_INDEX_HTML[] PROGMEM = R"rawliteral(<!DOCTYPE html>
<html lang="uk">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>HTRAM Standalone</title>
  <style>
    :root {
      --bg: #090d16;
      --card: #131b2e;
      --card-border: #1e293b;
      --text: #f1f5f9;
      --text-muted: #94a3b8;
      --primary: #38bdf8;
      --primary-hover: #0284c7;
      --success: #22c55e;
      --warning: #f59e0b;
      --danger: #ef4444;
      --radius: 12px;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    html, body {
      overflow-x: hidden;
      max-width: 100vw;
    }
    body {
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      padding: 16px;
      line-height: 1.5;
    }
    .container { max-width: 600px; margin: 0 auto; width: 100%; }
    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 20px;
      padding-bottom: 12px;
      border-bottom: 1px solid var(--card-border);
    }
    h1 { font-size: 1.5rem; font-weight: 700; color: #fff; display: flex; align-items: center; gap: 8px; }
    .badge {
      font-size: 0.75rem;
      padding: 3px 8px;
      border-radius: 9999px;
      font-weight: 600;
    }
    .badge-online { background: rgba(34, 197, 94, 0.2); color: var(--success); }
    .badge-offline { background: rgba(239, 68, 68, 0.2); color: var(--danger); }
    .badge-alert { background: rgba(239, 68, 68, 0.2); color: var(--danger); }
    .badge-clear { background: rgba(34, 197, 94, 0.2); color: var(--success); }
    .save-status { font-size: 0.75rem; padding: 2px 6px; border-radius: 4px; transition: all 0.25s ease; color: var(--success); font-weight: 500; }
    .save-status.saving { color: var(--warning); }
    .save-status.saved { color: var(--success); }
    .save-status.error { color: var(--danger); }
    
    .grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-bottom: 16px; }
    .card {
      background: var(--card);
      border: 1px solid var(--card-border);
      border-radius: var(--radius);
      padding: 16px;
      margin-bottom: 16px;
      overflow: hidden;
    }
    .sensor-card { padding: 14px; text-align: center; }
    .sensor-lbl { font-size: 0.8rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; }
    .sensor-val { font-size: 1.5rem; font-weight: 700; margin-top: 4px; }
    .sensor-unit { font-size: 0.85rem; font-weight: 400; color: var(--text-muted); }

    .card h2 { font-size: 1.1rem; font-weight: 600; margin-bottom: 12px; display: flex; align-items: center; justify-content: space-between; }
    .form-group { margin-bottom: 14px; }
    .form-group:last-child { margin-bottom: 0; }
    label { display: block; font-size: 0.85rem; color: var(--text-muted); margin-bottom: 6px; }
    select, input[type="text"], input[type="time"], input[type="number"] {
      width: 100%;
      max-width: 100%;
      box-sizing: border-box;
      background: #0b1120;
      border: 1px solid var(--card-border);
      border-radius: 8px;
      color: var(--text);
      padding: 10px 12px;
      font-size: 0.95rem;
      outline: none;
      color-scheme: dark;
    }
    select:focus, input:focus { border-color: var(--primary); }
    input[type="time"] {
      display: block;
      width: 100%;
      max-width: 100%;
      box-sizing: border-box;
      min-height: 42px;
    }

    .switch-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 6px 0;
    }
    .switch {
      position: relative;
      display: inline-block;
      width: 48px;
      height: 26px;
    }
    .switch input { opacity: 0; width: 0; height: 0; }
    .slider {
      position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0;
      background-color: #334155;
      transition: .3s;
      border-radius: 26px;
    }
    .slider:before {
      position: absolute; content: ""; height: 20px; width: 20px; left: 3px; bottom: 3px;
      background-color: white;
      transition: .3s;
      border-radius: 50%;
    }
    input:checked + .slider { background-color: var(--primary); }
    input:checked + .slider:before { transform: translateX(22px); }

    input[type="range"] {
      width: 100%;
      accent-color: var(--primary);
    }
    .range-val { font-size: 0.85rem; color: var(--text-muted); text-align: right; }

    .days-selector {
      display: grid;
      grid-template-columns: repeat(7, 1fr);
      gap: 6px;
      margin-top: 6px;
    }
    .day-check {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 8px 2px;
      background: #0b1120;
      border: 1px solid var(--card-border);
      border-radius: 8px;
      cursor: pointer;
      user-select: none;
      transition: all 0.2s;
      text-align: center;
      margin-bottom: 0;
    }
    .day-check:hover {
      border-color: var(--primary);
    }
    .day-check input[type="checkbox"] {
      cursor: pointer;
      accent-color: var(--primary);
      width: 16px;
      height: 16px;
      margin-bottom: 4px;
    }
    .day-check .day-name {
      font-size: 0.8rem;
      font-weight: 600;
      color: var(--text-muted);
    }
    .day-check:has(input:checked) {
      border-color: rgba(56, 189, 248, 0.4);
      background: rgba(56, 189, 248, 0.08);
    }
    .day-check:has(input:checked) .day-name {
      color: var(--primary);
    }

    .btn {
      width: 100%;
      background: var(--primary);
      color: #0b1120;
      border: none;
      padding: 12px;
      border-radius: 8px;
      font-size: 1rem;
      font-weight: 600;
      cursor: pointer;
      transition: background 0.2s;
    }
    .btn:hover { background: var(--primary-hover); }
    .btn-secondary { background: #1e293b; color: var(--text); margin-top: 8px; }
    .btn-secondary:hover { background: #334155; }
    .btn-danger { background: rgba(239, 68, 68, 0.2); color: var(--danger); border: 1px solid var(--danger); }
    .btn-danger:hover { background: var(--danger); color: white; }

    .toast {
      position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%);
      background: #1e293b; color: #fff; padding: 10px 20px; border-radius: 30px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.5); font-size: 0.9rem;
      opacity: 0; pointer-events: none; transition: opacity 0.3s; z-index: 100;
    }
    .toast.show { opacity: 1; }

    .alert-banner {
      background: rgba(239, 68, 68, 0.15);
      border: 1px solid var(--danger);
      color: #fca5a5;
      padding: 12px;
      border-radius: 8px;
      margin-bottom: 16px;
      display: none;
      align-items: center;
      gap: 10px;
      font-weight: 600;
    }
    .update-banner {
      background: rgba(56, 189, 248, 0.15);
      border: 1px solid var(--primary);
      padding: 12px;
      border-radius: 8px;
      margin-bottom: 16px;
      display: none;
    }

    .loc-badge-card {
      background: rgba(56, 189, 248, 0.08);
      border: 1px solid rgba(56, 189, 248, 0.25);
      border-radius: 8px;
      padding: 12px 14px;
      margin-bottom: 14px;
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .loc-badge-icon {
      font-size: 1.5rem;
      line-height: 1;
    }
    .loc-badge-name {
      font-weight: 700;
      color: #fff;
      font-size: 1.1rem;
    }
    .loc-badge-sub {
      font-size: 0.8rem;
      color: var(--text-muted);
      margin-top: 2px;
    }
    .search-container {
      position: relative;
      margin-bottom: 10px;
    }
    .search-input-wrap {
      position: relative;
      display: flex;
      align-items: center;
    }
    .search-input-wrap input {
      padding-right: 36px;
    }
    .search-spinner {
      position: absolute;
      right: 12px;
      width: 16px;
      height: 16px;
      border: 2px solid var(--text-muted);
      border-top-color: var(--primary);
      border-radius: 50%;
      animation: spin 0.6s linear infinite;
      display: none;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
    .search-dropdown {
      position: absolute;
      top: calc(100% + 4px);
      left: 0;
      right: 0;
      background: #1e293b;
      border: 1px solid var(--card-border);
      border-radius: 8px;
      max-height: 240px;
      overflow-y: auto;
      z-index: 50;
      box-shadow: 0 10px 25px rgba(0,0,0,0.5);
      display: none;
    }
    .search-dropdown.show { display: block; }
    .search-item {
      padding: 10px 14px;
      cursor: pointer;
      border-bottom: 1px solid rgba(255,255,255,0.05);
      transition: background 0.15s;
    }
    .search-item:last-child { border-bottom: none; }
    .search-item:hover, .search-item.active { background: #334155; }
    .search-item-title { font-weight: 600; color: #fff; font-size: 0.95rem; }
    .search-item-sub { font-size: 0.75rem; color: var(--text-muted); margin-top: 2px; }
    .quick-chips {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-bottom: 12px;
    }
    .chip {
      background: #0b1120;
      color: var(--text);
      border: 1px solid var(--card-border);
      border-radius: 16px;
      padding: 4px 10px;
      font-size: 0.8rem;
      cursor: pointer;
      transition: all 0.15s ease;
    }
    .chip:hover {
      background: #334155;
      border-color: var(--primary);
      color: #fff;
    }
    details summary {
      cursor: pointer;
      font-size: 0.85rem;
      color: var(--text-muted);
      user-select: none;
      padding: 4px 0;
    }
    details summary:hover { color: var(--text); }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div>
        <h1>HTRAM</h1>
        <div style="font-size: 0.75rem; color: var(--text-muted); display: flex; align-items: center; gap: 8px;">
          <span id="device-info">Автономна станція</span>
          <span id="save-status" class="save-status">● Збережено</span>
        </div>
      </div>
      <div>
        <span id="wifi-badge" class="badge badge-online">Wi-Fi OK</span>
      </div>
    </header>

    <div id="live-alert-banner" class="alert-banner">
      <span>⚠️</span>
      <span id="alert-banner-text">УВАГА: ПОВІТРЯНА ТРИВОГА!</span>
    </div>

    <div id="update-banner" class="update-banner">
      <div style="font-weight: 600; margin-bottom: 6px;" id="update-text">Доступне оновлення прошивки!</div>
      <button class="btn" onclick="triggerOtaUpdate()">Оновити в 1 клік</button>
    </div>

    <!-- Live Sensors -->
    <div class="grid">
      <div class="card sensor-card">
        <div class="sensor-lbl">Повітря (CO2)</div>
        <div class="sensor-val" id="val-co2">--</div>
        <div class="sensor-unit">ppm</div>
      </div>
      <div class="card sensor-card">
        <div class="sensor-lbl">Температура</div>
        <div class="sensor-val" id="val-temp">--</div>
        <div class="sensor-unit">°C</div>
      </div>
      <div class="card sensor-card">
        <div class="sensor-lbl">Вологість</div>
        <div class="sensor-val" id="val-hum">--</div>
        <div class="sensor-unit">%</div>
      </div>
      <div class="card sensor-card">
        <div class="sensor-lbl">Батарея</div>
        <div class="sensor-val" id="val-batt">--</div>
        <div class="sensor-unit" id="val-batt-sub">%</div>
      </div>
    </div>

    <!-- Повітряна тривога -->
    <div class="card">
      <h2>Повітряна тривога <span id="alert-status-badge" class="badge badge-clear">Відбій</span></h2>
      <div class="form-group">
        <label for="sel-region">Регіон сповіщення (район / місто / область):</label>
        <select id="sel-region" onchange="onRegionChange(parseInt(this.value))">
          <optgroup label="АР Крим">
            <option value="9999" data-lat="45.6857" data-lon="33.9329">АР Крим</option>
          </optgroup>
          <optgroup label="Вінницька область">
            <option value="4" data-lat="48.899" data-lon="28.5161">Вінницька обл.</option>
            <option value="32" data-lat="48.5007" data-lon="28.6465">Тульчинський район</option>
            <option value="35" data-lat="48.9175" data-lon="27.8781">Жмеринський район</option>
            <option value="36" data-lat="49.2421" data-lon="28.8848">Вінницький район</option>
            <option value="34" data-lat="49.6142" data-lon="28.3944">Хмільницький район</option>
            <option value="33" data-lat="48.4946" data-lon="27.9035">Могилів-Подільський район</option>
            <option value="37" data-lat="48.607" data-lon="29.5473">Гайсинський район</option>
            <option value="155" data-lat="49.232" data-lon="28.468">м. Вінниця + ТГ</option>
          </optgroup>
          <optgroup label="Волинська область">
            <option value="8" data-lat="51.5451" data-lon="24.6628">Волинська обл.</option>
            <option value="39" data-lat="50.7598" data-lon="25.4104">Луцький район</option>
            <option value="38" data-lat="50.8781" data-lon="24.3467">Володимир-Волинський район</option>
            <option value="40" data-lat="51.3894" data-lon="24.2896">Ковельський район</option>
            <option value="41" data-lat="51.5487" data-lon="25.173">Камінь-Каширський район</option>
            <option value="225" data-lat="50.7451" data-lon="25.3201">м. Луцьк + ТГ</option>
          </optgroup>
          <optgroup label="Дніпропетровська область">
            <option value="9" data-lat="48.6626" data-lon="34.9502">Дніпропетровська обл.</option>
            <option value="43" data-lat="48.8093" data-lon="35.2881">Новомосковський район</option>
            <option value="44" data-lat="48.5204" data-lon="34.9684">Дніпровський район</option>
            <option value="47" data-lat="47.7507" data-lon="34.4912">Нікопольський район</option>
            <option value="48" data-lat="48.2395" data-lon="36.0605">Синельниківський район</option>
            <option value="42" data-lat="48.4813" data-lon="34.1161">Кам'янський район</option>
            <option value="45" data-lat="48.6426" data-lon="35.9118">Павлоградський район</option>
            <option value="46" data-lat="47.8878" data-lon="33.5456">Криворізький район</option>
            <option value="332" data-lat="51.5567" data-lon="30.6122">м. Дніпро + ТГ</option>
          </optgroup>
          <optgroup label="Донецька область">
            <option value="28" data-lat="47.9213" data-lon="37.781">Донецька обл.</option>
            <option value="56" data-lat="48.204" data-lon="37.4461">Покровський район</option>
            <option value="51" data-lat="48.172" data-lon="38.3762">Горлівський район</option>
            <option value="55" data-lat="47.7162" data-lon="37.1579">Волноваський район</option>
            <option value="53" data-lat="47.9076" data-lon="38.207">Донецький район</option>
            <option value="49" data-lat="47.4729" data-lon="38.097">Кальміуський район</option>
            <option value="52" data-lat="47.1676" data-lon="37.4027">Маріупольський район</option>
            <option value="50" data-lat="48.7477" data-lon="37.4275">Краматорський район</option>
            <option value="54" data-lat="48.6498" data-lon="38.0225">Бахмутський район</option>
          </optgroup>
          <optgroup label="Житомирська область">
            <option value="10" data-lat="50.9081" data-lon="28.3868">Житомирська обл.</option>
            <option value="59" data-lat="50.2479" data-lon="28.7752">Житомирський район</option>
            <option value="58" data-lat="51.1624" data-lon="28.3448">Коростенський район</option>
            <option value="57" data-lat="49.8687" data-lon="28.4968">Бердичівський район</option>
            <option value="60" data-lat="50.6262" data-lon="27.7008">Звягельський район</option>
            <option value="442" data-lat="50.2601" data-lon="28.6696">м. Житомир + ТГ</option>
          </optgroup>
          <optgroup label="Закарпатська область">
            <option value="11" data-lat="48.2954" data-lon="23.4466">Закарпатська обл.</option>
            <option value="66" data-lat="48.7258" data-lon="22.6098">Ужгородський район</option>
            <option value="61" data-lat="48.1798" data-lon="22.8739">Берегівський район</option>
            <option value="62" data-lat="48.3692" data-lon="23.3201">Хустський район</option>
            <option value="63" data-lat="48.1474" data-lon="24.2367">Рахівський район</option>
            <option value="64" data-lat="48.2474" data-lon="23.8111">Тячівський район</option>
            <option value="65" data-lat="48.6029" data-lon="22.9252">Мукачівський район</option>
            <option value="500" data-lat="48.6224" data-lon="22.3023">м. Ужгород + ТГ</option>
          </optgroup>
          <optgroup label="Запорізька область">
            <option value="12" data-lat="47.4165" data-lon="35.923">Запорізька обл.</option>
            <option value="146" data-lat="47.3706" data-lon="34.9358">Василівський район</option>
            <option value="145" data-lat="47.4241" data-lon="36.4483">Пологівський район</option>
            <option value="149" data-lat="47.8248" data-lon="35.34">Запорізький район</option>
            <option value="147" data-lat="46.9121" data-lon="36.5441">Бердянський район</option>
            <option value="148" data-lat="46.7331" data-lon="35.3124">Мелітопольський район</option>
            <option value="564" data-lat="47.8508" data-lon="35.1183">м. Запоріжжя + ТГ</option>
          </optgroup>
          <optgroup label="Івано-Франківська область">
            <option value="13" data-lat="48.7482" data-lon="24.5207">Ів.-Франківська обл.</option>
            <option value="68" data-lat="49.0337" data-lon="24.7517">Івано-Франківський район</option>
            <option value="67" data-lat="48.0012" data-lon="24.7427">Верховинський район</option>
            <option value="71" data-lat="48.8454" data-lon="23.9647">Калуський район</option>
            <option value="72" data-lat="48.4372" data-lon="24.4385">Надвірнянський район</option>
            <option value="70" data-lat="48.6151" data-lon="25.1861">Коломийський район</option>
            <option value="69" data-lat="48.3088" data-lon="24.9865">Косівський район</option>
            <option value="632" data-lat="48.9225" data-lon="24.7103">м. Івано-Франківськ + ТГ</option>
          </optgroup>
          <optgroup label="Київська область">
            <option value="14" data-lat="50.1786" data-lon="30.4925">Київська обл.</option>
            <option value="77" data-lat="50.1405" data-lon="29.9425">Фастівський район</option>
            <option value="73" data-lat="49.6479" data-lon="30.105">Білоцерківський район</option>
            <option value="75" data-lat="50.5449" data-lon="29.8987">Бучанський район</option>
            <option value="76" data-lat="49.8792" data-lon="30.9336">Обухівський район</option>
            <option value="74" data-lat="51.0362" data-lon="29.991">Вишгородський район</option>
            <option value="79" data-lat="50.474" data-lon="31.5361">Броварський район</option>
            <option value="78" data-lat="50.1631" data-lon="31.0949">Бориспільський район</option>
            <option value="31" data-lat="50.45" data-lon="30.5241">м. Київ</option>
          </optgroup>
          <optgroup label="Кіровоградська область">
            <option value="15" data-lat="48.1917" data-lon="31.6903">Кіровоградська обл.</option>
            <option value="81" data-lat="48.4162" data-lon="32.5015">Кропивницький район</option>
            <option value="80" data-lat="48.6695" data-lon="33.2849">Олександрійський район</option>
            <option value="82" data-lat="48.4561" data-lon="30.4679">Голованівський район</option>
            <option value="83" data-lat="48.5003" data-lon="31.3767">Новоукраїнський район</option>
            <option value="761" data-lat="48.5106" data-lon="32.2656">м. Кропивницький + ТГ</option>
          </optgroup>
          <optgroup label="Луганська область">
            <option value="16" data-lat="49.2725" data-lon="38.915">Луганська обл.</option>
            <option value="86" data-lat="49.4329" data-lon="39.4633">Старобільський район</option>
            <option value="85" data-lat="49.6079" data-lon="38.424">Сватівський район</option>
            <option value="84" data-lat="49.0329" data-lon="38.3726">Сєвєродонецький район</option>
            <option value="87" data-lat="48.8509" data-lon="39.3581">Щастинський район</option>
          </optgroup>
          <optgroup label="Львівська область">
            <option value="27" data-lat="49.6512" data-lon="23.8267">Львівська обл.</option>
            <option value="90" data-lat="49.9109" data-lon="24.1805">Львівський район</option>
            <option value="89" data-lat="49.1885" data-lon="23.9776">Стрийський район</option>
            <option value="88" data-lat="49.2956" data-lon="22.9314">Самбірський район</option>
            <option value="91" data-lat="49.2875" data-lon="23.4157">Дрогобицький район</option>
            <option value="92" data-lat="50.3737" data-lon="24.2117">Червоноградський район</option>
            <option value="94" data-lat="49.9493" data-lon="24.9236">Золочівський район</option>
            <option value="93" data-lat="49.9117" data-lon="23.4968">Яворівський район</option>
            <option value="845" data-lat="49.842" data-lon="24.0316">м. Львів + ТГ</option>
          </optgroup>
          <optgroup label="Миколаївська область">
            <option value="17" data-lat="47.3886" data-lon="31.9442">Миколаївська обл.</option>
            <option value="96" data-lat="47.4332" data-lon="32.5541">Баштанський район</option>
            <option value="95" data-lat="47.6388" data-lon="31.4898">Вознесенський район</option>
            <option value="97" data-lat="49.3455" data-lon="36.3923">Первомайський район</option>
            <option value="98" data-lat="46.9626" data-lon="31.78">Миколаївський район</option>
            <option value="926" data-lat="46.9759" data-lon="31.994">м. Миколаїв + ТГ</option>
          </optgroup>
          <optgroup label="Одеська область">
            <option value="18" data-lat="46.1147" data-lon="29.9567">Одеська обл.</option>
            <option value="105" data-lat="46.0111" data-lon="29.2695">Болградський район</option>
            <option value="100" data-lat="47.2074" data-lon="30.6502">Березівський район</option>
            <option value="104" data-lat="46.5335" data-lon="30.3214">Одеський район</option>
            <option value="102" data-lat="46.0138" data-lon="29.9732">Білгород-Дністровський район</option>
            <option value="103" data-lat="47.0719" data-lon="29.8685">Роздільнянський район</option>
            <option value="101" data-lat="45.5069" data-lon="29.1975">Ізмаїльський район</option>
            <option value="99" data-lat="47.7715" data-lon="29.8403">Подільський район</option>
            <option value="964" data-lat="46.4843" data-lon="30.7323">м. Одеса + ТГ</option>
          </optgroup>
          <optgroup label="Полтавська область">
            <option value="19" data-lat="49.8608" data-lon="33.7499">Полтавська обл.</option>
            <option value="107" data-lat="49.3454" data-lon="33.223">Кременчуцький район</option>
            <option value="106" data-lat="50.0221" data-lon="32.8484">Лубенський район</option>
            <option value="109" data-lat="49.5455" data-lon="34.5568">Полтавський район</option>
            <option value="108" data-lat="50.0323" data-lon="33.7921">Миргородський район</option>
            <option value="1060" data-lat="49.5897" data-lon="34.5508">м. Полтава + ТГ</option>
          </optgroup>
          <optgroup label="Рівненська область">
            <option value="5" data-lat="51.2074" data-lon="26.5208">Рівненська обл.</option>
            <option value="110" data-lat="51.5675" data-lon="25.9496">Вараський район</option>
            <option value="111" data-lat="50.3644" data-lon="25.5664">Дубенський район</option>
            <option value="112" data-lat="50.6891" data-lon="26.5622">Рівненський район</option>
            <option value="113" data-lat="51.4108" data-lon="26.9704">Сарненський район</option>
            <option value="1133" data-lat="50.6196" data-lon="26.2513">м. Рівне + ТГ</option>
          </optgroup>
          <optgroup label="Сумська область">
            <option value="20" data-lat="50.7697" data-lon="34.3289">Сумська обл.</option>
            <option value="115" data-lat="51.9047" data-lon="33.7202">Шосткинський район</option>
            <option value="116" data-lat="50.7648" data-lon="33.6763">Роменський район</option>
            <option value="117" data-lat="51.3384" data-lon="33.6817">Конотопський район</option>
            <option value="114" data-lat="50.8215" data-lon="34.7912">Сумський район</option>
            <option value="118" data-lat="50.432" data-lon="35.047">Охтирський район</option>
            <option value="1187" data-lat="50.912" data-lon="34.8028">м. Суми + ТГ</option>
          </optgroup>
          <optgroup label="Тернопільська область">
            <option value="21" data-lat="49.663" data-lon="25.6168">Тернопільська обл.</option>
            <option value="119" data-lat="49.5344" data-lon="25.4428">Тернопільський район</option>
            <option value="121" data-lat="48.946" data-lon="25.6751">Чортківський район</option>
            <option value="120" data-lat="49.9812" data-lon="25.5168">Кременецький район</option>
            <option value="1241" data-lat="49.5558" data-lon="25.5924">м. Тернопіль + ТГ</option>
          </optgroup>
          <optgroup label="Харківська область">
            <option value="22" data-lat="49.83" data-lon="36.3789">Харківська обл.</option>
            <option value="124" data-lat="49.9941" data-lon="36.23">Харківський район</option>
            <option value="123" data-lat="49.8814" data-lon="37.6177">Куп'янський район</option>
            <option value="122" data-lat="49.9591" data-lon="36.8901">Чугуївський район</option>
            <option value="126" data-lat="50.0482" data-lon="35.366">Богодухівський район</option>
            <option value="127" data-lat="49.3168" data-lon="35.6553">Красноградський район</option>
            <option value="125" data-lat="49.1976" data-lon="37.0714">Ізюмський район</option>
            <option value="128" data-lat="49.0365" data-lon="36.3699">Лозівський район</option>
            <option value="1293" data-lat="49.9923" data-lon="36.231">м. Харків + ТГ</option>
          </optgroup>
          <optgroup label="Херсонська область">
            <option value="23" data-lat="46.5422" data-lon="33.4079">Херсонська обл.</option>
            <option value="131" data-lat="46.8093" data-lon="33.7265">Каховський район</option>
            <option value="129" data-lat="47.1711" data-lon="33.4043">Бериславський район</option>
            <option value="130" data-lat="46.2976" data-lon="32.2979">Скадовський район</option>
            <option value="132" data-lat="46.6355" data-lon="32.5342">Херсонський район</option>
            <option value="133" data-lat="46.4285" data-lon="34.5761">Генічеський район</option>
            <option value="1370" data-lat="46.6401" data-lon="32.6144">м. Херсон + ТГ</option>
          </optgroup>
          <optgroup label="Хмельницька область">
            <option value="3" data-lat="49.2686" data-lon="27.0636">Хмельницька обл.</option>
            <option value="136" data-lat="50.138" data-lon="27.1639">Шепетівський район</option>
            <option value="134" data-lat="49.4326" data-lon="27.0042">Хмельницький район</option>
            <option value="135" data-lat="48.8135" data-lon="26.8341">Кам'янець-Подільський район</option>
            <option value="1400" data-lat="49.4196" data-lon="26.9794">м. Хмельницький + ТГ</option>
          </optgroup>
          <optgroup label="Черкаська область">
            <option value="24" data-lat="49.146" data-lon="31.2272">Черкаська обл.</option>
            <option value="153" data-lat="49.774" data-lon="32.1259">Золотоніський район</option>
            <option value="152" data-lat="49.4362" data-lon="31.7603">Черкаський район</option>
            <option value="150" data-lat="49.1023" data-lon="31.0739">Звенигородський район</option>
            <option value="151" data-lat="48.8935" data-lon="30.0829">Уманський район</option>
            <option value="1473" data-lat="49.4447" data-lon="32.0588">м. Черкаси + ТГ</option>
          </optgroup>
          <optgroup label="Чернівецька область">
            <option value="26" data-lat="48.3811" data-lon="26.1082">Чернівецька обл.</option>
            <option value="139" data-lat="48.4199" data-lon="26.5284">Дністровський район</option>
            <option value="138" data-lat="48.0642" data-lon="25.163">Вижницький район</option>
            <option value="137" data-lat="48.3009" data-lon="26.0578">Чернівецький район</option>
            <option value="1542" data-lat="48.2865" data-lon="25.9377">м. Чернівці + ТГ</option>
          </optgroup>
          <optgroup label="Чернігівська область">
            <option value="25" data-lat="51.2726" data-lon="31.7417">Чернігівська обл.</option>
            <option value="141" data-lat="51.8499" data-lon="32.9947">Новгород-Сіверський район</option>
            <option value="142" data-lat="50.9815" data-lon="31.7304">Ніжинський район</option>
            <option value="143" data-lat="50.7147" data-lon="32.5992">Прилуцький район</option>
            <option value="140" data-lat="51.4385" data-lon="31.2063">Чернігівський район</option>
            <option value="144" data-lat="51.7298" data-lon="32.268">Корюківський район</option>
            <option value="1591" data-lat="51.4941" data-lon="31.2943">м. Чернігів + ТГ</option>
          </optgroup>
        </select>
      </div>
      <div style="font-size: 0.8rem; color: var(--text-muted); line-height: 1.4;">
        ℹ️ <strong>Точні районні сповіщення:</strong> завдяки JAAM Fusion пристрій реагує окремо на ваш район/громаду, а також на загальнообласні тривоги, розрізняючи дрони, ракети та артобстріл.
      </div>
    </div>

    <!-- Прогноз погоди та Локація -->
    <div class="card">
      <h2>Погода та Локація</h2>

      <!-- Активний населений пункт -->
      <div class="loc-badge-card">
        <div class="loc-badge-icon">📍</div>
        <div style="flex: 1; min-width: 0;">
          <div class="loc-badge-name" id="loc-display-name">Київ</div>
          <div class="loc-badge-sub" id="loc-display-sub">м. Київ • 50.4501, 30.5234</div>
        </div>
      </div>

      <!-- Пошук населеного пункту -->
      <div class="form-group" style="margin-bottom: 12px;">
        <label for="inp-city-search">Знайти місто або село:</label>
        <div class="search-container">
          <div class="search-input-wrap">
            <input type="text" id="inp-city-search" placeholder="Введіть назву (наприклад: Бровари, Умань, Яремче...)" autocomplete="off" oninput="onCitySearchInput(this.value)">
            <div id="search-spinner" class="search-spinner"></div>
          </div>
          <div id="city-search-results" class="search-dropdown"></div>
        </div>
      </div>

      <!-- Швидкий вибір (Популярні міста) -->
      <div class="form-group" style="margin-bottom: 12px;">
        <div style="font-size: 0.8rem; color: var(--text-muted); margin-bottom: 6px;">Швидкий вибір:</div>
        <div class="quick-chips">
          <button type="button" class="chip" onclick="selectCityQuick('Київ', 50.4547, 30.5238, 31, 'м. Київ')">Київ</button>
          <button type="button" class="chip" onclick="selectCityQuick('Львів', 49.8429, 24.0311, 845, 'м. Львів + ТГ')">Львів</button>
          <button type="button" class="chip" onclick="selectCityQuick('Одеса', 46.4825, 30.7233, 964, 'м. Одеса + ТГ')">Одеса</button>
          <button type="button" class="chip" onclick="selectCityQuick('Харків', 49.9935, 36.2304, 1293, 'м. Харків + ТГ')">Харків</button>
          <button type="button" class="chip" onclick="selectCityQuick('Дніпро', 48.4647, 35.0462, 332, 'м. Дніпро + ТГ')">Дніпро</button>
          <button type="button" class="chip" onclick="selectCityQuick('Вінниця', 49.2331, 28.4682, 155, 'м. Вінниця + ТГ')">Вінниця</button>
          <button type="button" class="chip" onclick="selectCityQuick('Запоріжжя', 47.8388, 35.1396, 564, 'м. Запоріжжя + ТГ')">Запоріжжя</button>
          <button type="button" class="chip" onclick="selectCityQuick('Полтава', 49.5883, 34.5514, 1060, 'м. Полтава + ТГ')">Полтава</button>
          <button type="button" class="chip" onclick="selectCityQuick('Черкаси', 49.4444, 32.0598, 1473, 'м. Черкаси + ТГ')">Черкаси</button>
          <button type="button" class="chip" onclick="selectCityQuick('Ів.-Франківськ', 48.9226, 24.7111, 632, 'м. Івано-Франківськ + ТГ')">Ів.-Франківськ</button>
          <button type="button" class="chip" onclick="selectCityQuick('Тернопіль', 49.5535, 25.5948, 1241, 'м. Тернопіль + ТГ')">Тернопіль</button>
        </div>
      </div>

      <!-- Кнопка автовизначення за IP -->
      <button type="button" class="btn btn-secondary" style="margin-bottom: 12px; display: flex; align-items: center; justify-content: center; gap: 8px; font-size: 0.9rem; padding: 10px;" onclick="autoDetectLocation()">
        <span>📍</span> <span>Визначити локацію автоматично (по IP)</span>
      </button>

      <!-- Ручні координати для експертів (згорнуто) -->
      <details style="margin-top: 10px; border-top: 1px solid var(--card-border); padding-top: 10px;">
        <summary>⚙️ Ручні координати (Lat / Lon)</summary>
        <div class="grid" style="margin-top: 10px; margin-bottom: 0;">
          <div class="form-group">
            <label for="inp-lat">Широта (Lat):</label>
            <input type="number" step="0.0001" id="inp-lat" onchange="onCustomCoordsChange()">
          </div>
          <div class="form-group">
            <label for="inp-lon">Довгота (Lon):</label>
            <input type="number" step="0.0001" id="inp-lon" onchange="onCustomCoordsChange()">
          </div>
        </div>
      </details>

      <div style="font-size: 0.8rem; color: var(--text-muted); margin-top: 8px;">
        Джерело: Open-Meteo API (безкоштовно, без ключів).
      </div>
    </div>

    <!-- Будильник і Хвилина мовчання -->
    <div class="card">
      <h2>Будильник та Меморіал</h2>
      <div class="switch-row">
        <span>Будильник увімкнено</span>
        <label class="switch">
          <input type="checkbox" id="chk-alarm" onchange="autoSave({ alarm_enabled: this.checked })">
          <span class="slider"></span>
        </label>
      </div>
      <div class="form-group" style="margin-top: 10px;">
        <label for="inp-alarm-time">Час будильника:</label>
        <input type="time" id="inp-alarm-time" onchange="autoSave({ alarm_time: this.value })">
      </div>
      <div class="form-group" style="margin-top: 10px;">
        <label>Дні тижня:</label>
        <div class="days-selector" id="alarm-days-group">
          <label class="day-check" for="chk-day-1">
            <input type="checkbox" id="chk-day-1" onchange="onAlarmDaysChange()">
            <span class="day-name">Пн</span>
          </label>
          <label class="day-check" for="chk-day-2">
            <input type="checkbox" id="chk-day-2" onchange="onAlarmDaysChange()">
            <span class="day-name">Вт</span>
          </label>
          <label class="day-check" for="chk-day-3">
            <input type="checkbox" id="chk-day-3" onchange="onAlarmDaysChange()">
            <span class="day-name">Ср</span>
          </label>
          <label class="day-check" for="chk-day-4">
            <input type="checkbox" id="chk-day-4" onchange="onAlarmDaysChange()">
            <span class="day-name">Чт</span>
          </label>
          <label class="day-check" for="chk-day-5">
            <input type="checkbox" id="chk-day-5" onchange="onAlarmDaysChange()">
            <span class="day-name">Пт</span>
          </label>
          <label class="day-check" for="chk-day-6">
            <input type="checkbox" id="chk-day-6" onchange="onAlarmDaysChange()">
            <span class="day-name">Сб</span>
          </label>
          <label class="day-check" for="chk-day-7">
            <input type="checkbox" id="chk-day-7" onchange="onAlarmDaysChange()">
            <span class="day-name">Нд</span>
          </label>
        </div>
      </div>
      <hr style="border: 0; border-top: 1px solid var(--card-border); margin: 14px 0;">
      <div class="switch-row">
        <div>
          <div>Хвилина мовчання (09:00)</div>
          <div style="font-size: 0.8rem; color: var(--text-muted);">Метроном та Гімн щодня о 09:00:00</div>
        </div>
        <label class="switch">
          <input type="checkbox" id="chk-silence" onchange="autoSave({ silence_enabled: this.checked })">
          <span class="slider"></span>
        </label>
      </div>
    </div>

    <!-- Екран та світлодіоди -->
    <div class="card">
      <h2>Екран та Світлодіоди</h2>
      <div class="form-group">
        <label for="rng-brightness">Яскравість дисплея: <span id="lbl-brightness">100</span>%</label>
        <input type="range" id="rng-brightness" min="5" max="100" step="1" oninput="onBrightnessInput(this.value)">
      </div>
      <div class="switch-row" style="margin-top: 10px;">
        <div>
          <div>Авто-індикація CO2 (LED)</div>
          <div style="font-size: 0.8rem; color: var(--text-muted);">Кольори світлодіодів за рівнем CO2</div>
        </div>
        <label class="switch">
          <input type="checkbox" id="chk-led-auto" onchange="onLedAutoToggle(this.checked)">
          <span class="slider"></span>
        </label>
      </div>
      <div id="co2-thresholds-container" style="margin-top: 12px; padding: 12px; background: rgba(11, 17, 32, 0.7); border-radius: 8px; border: 1px solid var(--card-border); transition: opacity 0.2s;">
        <div style="font-size: 0.85rem; font-weight: 600; margin-bottom: 8px; color: var(--text);">Пороги індикації CO2:</div>
        <div class="grid" style="margin-bottom: 0;">
          <div class="form-group">
            <label for="inp-co2-yellow" style="color: #f59e0b;">🟡 Жовтий від (ppm):</label>
            <input type="number" id="inp-co2-yellow" min="600" max="2500" step="50" onchange="autoSave({ co2_yellow: parseInt(this.value) || 1000 })">
          </div>
          <div class="form-group">
            <label for="inp-co2-red" style="color: #ef4444;">🔴 Червоний від (ppm):</label>
            <input type="number" id="inp-co2-red" min="800" max="5000" step="50" onchange="autoSave({ co2_red: parseInt(this.value) || 1500 })">
          </div>
        </div>
        <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 6px;">
          🟢 Зелений: &lt; жовтого | 🟡 Жовтий: норма | 🔴 Червоний: провітрити
        </div>
      </div>
      <div class="form-group" style="margin-top: 14px;">
        <label for="inp-trim">Калібрування температури (°C):</label>
        <input type="number" step="0.1" min="-10" max="10" id="inp-trim" onchange="autoSave({ temp_trim: parseFloat(this.value) || 0.0 })">
      </div>
    </div>

    <!-- Підказка автозбереження -->
    <div style="text-align: center; padding: 6px; color: var(--text-muted); font-size: 0.85rem; margin-bottom: 8px;">
      ⚡ Усі налаштування застосовуються та зберігаються миттєво
    </div>

    <!-- Мережа Wi-Fi -->
    <div class="card" style="margin-top: 16px;">
      <h2>Мережа Wi-Fi</h2>
      <div style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 12px;">
        Поточна мережа: <strong style="color: #fff;" id="lbl-wifi-current">--</strong>
      </div>
      <div class="form-group">
        <label for="inp-wifi-ssid">Назва мережі (SSID):</label>
        <input type="text" id="inp-wifi-ssid" placeholder="Введіть назву нової мережі" autocomplete="off">
      </div>
      <div class="form-group" style="margin-top: 10px;">
        <label for="inp-wifi-pass">Пароль Wi-Fi:</label>
        <div style="position: relative; display: flex; align-items: center;">
          <input type="password" id="inp-wifi-pass" placeholder="Пароль (залиште порожнім, якщо відкрита)" autocomplete="new-password" style="padding-right: 42px;">
          <button type="button" onclick="toggleWifiPassVisibility()" style="position: absolute; right: 8px; background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 1.1rem; padding: 4px;" title="Показати/приховати пароль">👁️</button>
        </div>
      </div>
      <div style="font-size: 0.8rem; color: var(--warning); margin-top: 10px; line-height: 1.4;">
        ⚠️ <strong>Увага:</strong> після збереження годинник перезавантажиться для підключення. Якщо параметри будуть невірними або мережа недоступна, увімкнеться точка доступу <strong>HTRAM Setup</strong> для налаштування (або натисніть кнопку 4 рази).
      </div>
      <button class="btn btn-secondary" style="margin-top: 14px; background: var(--primary); color: #000; font-weight: 600;" onclick="saveWifiSettings()">Зберегти та перепідключитись</button>
    </div>

    <!-- Оновлення та Інфо -->
    <div class="card" style="margin-top: 16px;">
      <h2>Система</h2>
      <div style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 12px;">
        Версія прошивки: <strong style="color: #fff;" id="lbl-version">--</strong><br>
        GD32 версія: <strong style="color: #fff;" id="lbl-gd32-ver">--</strong><br>
        IP адреса: <strong style="color: #fff;" id="lbl-ip">--</strong>
      </div>
      <button class="btn btn-secondary" onclick="checkUpdates()">Перевірити оновлення</button>
      <button class="btn btn-secondary btn-danger" style="margin-top: 8px;" onclick="rebootDevice()">Перезавантажити пристрій</button>
    </div>
  </div>

  <div id="toast" class="toast">Налаштування збережено!</div>

  <script>
    // Unregister legacy service workers (e.g. from previous ESPHome web_server)
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.getRegistrations().then(function(registrations) {
        for (let r of registrations) { r.unregister(); }
      });
    }

    let currentSettings = {};
    let brightnessDebounce = null;
    let saveTimeout = null;

    function setSaveStatus(state, text) {
      const el = document.getElementById('save-status');
      if (!el) return;
      el.className = 'save-status ' + state;
      el.textContent = text;
      clearTimeout(saveTimeout);
      if (state === 'saved') {
        saveTimeout = setTimeout(() => {
          if (el.className.includes('saved')) {
            el.className = 'save-status';
            el.textContent = '● Збережено';
          }
        }, 2000);
      }
    }

    async function autoSave(patch) {
      setSaveStatus('saving', '⟳ Збереження...');
      try {
        const res = await fetch('/api/settings', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(patch)
        });
        if (res.ok) {
          setSaveStatus('saved', '✓ Збережено');
          Object.assign(currentSettings, patch);
        } else {
          setSaveStatus('error', '⚠ Помилка');
        }
      } catch (e) {
        setSaveStatus('error', '⚠ Помилка зв\'язку');
      }
    }

    function onBrightnessInput(val) {
      document.getElementById('lbl-brightness').textContent = val;
      clearTimeout(brightnessDebounce);
      brightnessDebounce = setTimeout(() => {
        autoSave({ brightness: parseInt(val) });
      }, 100);
    }

    function escapeHtml(s) {
      if (!s) return '';
      return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function updateLocationDisplay(city, regionIdx, lat, lon, adminStr) {
      const nameEl = document.getElementById('loc-display-name');
      const subEl = document.getElementById('loc-display-sub');
      if (!nameEl || !subEl) return;

      nameEl.textContent = city || 'Не вказано';

      let regionName = '';
      const selRegion = document.getElementById('sel-region');
      if (selRegion) {
        for (let i = 0; i < selRegion.options.length; i++) {
          if (parseInt(selRegion.options[i].value) === parseInt(regionIdx)) {
            regionName = selRegion.options[i].text;
            break;
          }
        }
      }

      const parts = [];
      if (adminStr) {
        parts.push(adminStr);
      } else if (regionName) {
        parts.push(regionName);
      }

      if (lat != null && lon != null && !isNaN(lat) && !isNaN(lon)) {
        parts.push(`${parseFloat(lat).toFixed(4)}, ${parseFloat(lon).toFixed(4)}`);
      }

      subEl.textContent = parts.join(' • ') || 'Україна';
    }

    async function onRegionChange(regionIdx) {
      const sel = document.getElementById('sel-region');
      const opt = sel ? sel.options[sel.selectedIndex] : null;
      let city = document.getElementById('loc-display-name').textContent;
      let lat = parseFloat(document.getElementById('inp-lat').value);
      let lon = parseFloat(document.getElementById('inp-lon').value);
      if (opt) {
        const optLat = parseFloat(opt.getAttribute('data-lat'));
        const optLon = parseFloat(opt.getAttribute('data-lon'));
        if (!isNaN(optLat) && !isNaN(optLon)) {
          lat = optLat;
          lon = optLon;
          document.getElementById('inp-lat').value = lat.toFixed(4);
          document.getElementById('inp-lon').value = lon.toFixed(4);
        }
      }
      updateLocationDisplay(city, regionIdx, lat, lon);
      await autoSave({ region: regionIdx, lat, lon, city });
      setTimeout(fetchStatus, 300);
    }

    let searchDebounce = null;
    function onCitySearchInput(query) {
      clearTimeout(searchDebounce);
      const spinner = document.getElementById('search-spinner');
      const dropdown = document.getElementById('city-search-results');
      query = (query || '').trim();
      if (query.length < 2) {
        dropdown.classList.remove('show');
        dropdown.innerHTML = '';
        if (spinner) spinner.style.display = 'none';
        return;
      }
      if (spinner) spinner.style.display = 'block';
      searchDebounce = setTimeout(async () => {
        try {
          const results = await searchPlaces(query);
          renderSearchResults(results);
        } catch (e) {
          dropdown.innerHTML = '<div style="padding: 10px; color: var(--text-muted); font-size: 0.85rem;">Помилка пошуку</div>';
          dropdown.classList.add('show');
        } finally {
          if (spinner) spinner.style.display = 'none';
        }
      }, 300);
    }

    function deduplicateResults(items) {
      if (!items || !items.length) return [];
      const seen = new Set();
      const deduped = [];
      for (const item of items) {
        const name = (item.name || '').toLowerCase().trim();
        const admin2 = (item.admin2 || '').toLowerCase().trim();
        const admin1 = (item.admin1 || '').toLowerCase().trim();
        const key = `${name}|${admin2}|${admin1}`;
        if (!seen.has(key)) {
          seen.add(key);
          deduped.push(item);
        }
      }
      return deduped;
    }

    async function searchPlaces(query) {
      query = query.trim().replace(/['`ʼ]/g, '’');
      // 1. Пріоритет: Photon (OpenStreetMap геокодер від Komoot) - швидкий, знає всі села, хутори та райони України
      try {
        const url = `https://photon.komoot.io/api/?q=${encodeURIComponent(query)}&limit=12&osm_tag=place&osm_tag=boundary:administrative`;
        const res = await fetch(url);
        if (res.ok) {
          const data = await res.json();
          const uaFeatures = (data.features || []).filter(f => {
            const p = f.properties || {};
            const cc = (p.countrycode || '').toUpperCase();
            if (cc !== 'UA' && p.country !== 'Україна') return false;
            if (p.osm_key !== 'place' && p.osm_key !== 'boundary') return false;
            if (['railway', 'tourism', 'amenity', 'highway', 'shop', 'leisure', 'building'].includes(p.osm_key)) return false;
            if (p.type === 'house' || p.osm_value === 'historic') return false;
            return true;
          });
          if (uaFeatures.length > 0) {
            const mapped = uaFeatures.map(f => {
              const p = f.properties || {};
              const coords = (f.geometry && f.geometry.coordinates) || [0, 0];
              return {
                name: p.name || query,
                admin1: p.state || '',
                admin2: p.county || '',
                municipality: (p.city && p.city !== p.name) ? p.city : '',
                latitude: coords[1],
                longitude: coords[0]
              };
            });
            const deduped = deduplicateResults(mapped);
            if (deduped.length > 0) return deduped;
          }
        }
      } catch (e1) {}

      // 2. Fallback: Nominatim (прямий OpenStreetMap пошук по базі України)
      try {
        const url = `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(query)}&format=json&countrycodes=ua&accept-language=uk&limit=6&addressdetails=1`;
        const res = await fetch(url);
        if (res.ok) {
          const data = await res.json();
          if (Array.isArray(data) && data.length > 0) {
            const mapped = data.map(r => {
              const addr = r.address || {};
              const name = r.name || addr.village || addr.town || addr.city || (r.display_name ? r.display_name.split(',')[0].trim() : query);
              return {
                name: name,
                admin1: addr.state || '',
                admin2: addr.county || addr.district || '',
                municipality: addr.municipality || '',
                latitude: parseFloat(r.lat),
                longitude: parseFloat(r.lon)
              };
            });
            return deduplicateResults(mapped);
          }
        }
      } catch (e2) {}

      // 3. Fallback: Open-Meteo Geocoding
      try {
        const url = `https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(query)}&count=6&language=uk&format=json`;
        const res = await fetch(url);
        if (res.ok) {
          const data = await res.json();
          const items = (data.results || []).filter(r => r.country_code === 'UA' || r.country === 'Україна');
          return deduplicateResults(items.map(r => ({
            name: r.name,
            admin1: r.admin1 || '',
            admin2: r.admin2 || '',
            municipality: '',
            latitude: parseFloat(r.latitude),
            longitude: parseFloat(r.longitude)
          })));
        }
      } catch (e3) {}

      return [];
    }

    function renderSearchResults(items) {
      const dropdown = document.getElementById('city-search-results');
      dropdown.innerHTML = '';
      if (!items || items.length === 0) {
        dropdown.innerHTML = '<div style="padding: 10px; color: var(--text-muted); font-size: 0.85rem;">Населений пункт не знайдено</div>';
        dropdown.classList.add('show');
        return;
      }
      items.forEach(item => {
        const div = document.createElement('div');
        div.className = 'search-item';
        const adminParts = [item.admin2, item.municipality, item.admin1].filter(Boolean);
        const admin = adminParts.join(', ');
        div.innerHTML = `
          <div class="search-item-title">${escapeHtml(item.name)}</div>
          <div class="search-item-sub">${escapeHtml(admin || 'Україна')}</div>
        `;
        div.onclick = () => selectSettlement(item);
        dropdown.appendChild(div);
      });
      dropdown.classList.add('show');
    }

    async function selectSettlement(item) {
      const lat = parseFloat(item.latitude);
      const lon = parseFloat(item.longitude);
      const city = item.name;
      const adminParts = [item.admin2, item.municipality, item.admin1].filter(Boolean);
      const admin = adminParts.join(', ');

      const dropdown = document.getElementById('city-search-results');
      dropdown.classList.remove('show');
      dropdown.innerHTML = '';
      document.getElementById('inp-city-search').value = '';

      let regionIdx = detectJaamDistrict(lat, lon, item.admin2 || '', item.admin1 || '', city);
      document.getElementById('sel-region').value = regionIdx;

      document.getElementById('inp-lat').value = lat.toFixed(4);
      document.getElementById('inp-lon').value = lon.toFixed(4);

      updateLocationDisplay(city, regionIdx, lat, lon, admin);

      const patch = { lat, lon, city, region: regionIdx };
      await autoSave(patch);
      setTimeout(fetchStatus, 300);
      showToast(`Встановлено: ${city} (${item.admin2 || item.admin1 || ''})`);
    }

    async function selectCityQuick(city, lat, lon, regionIdx, regionName) {
      document.getElementById('inp-lat').value = lat.toFixed(4);
      document.getElementById('inp-lon').value = lon.toFixed(4);
      document.getElementById('sel-region').value = regionIdx;
      updateLocationDisplay(city, regionIdx, lat, lon, regionName);
      await autoSave({ lat, lon, city, region: regionIdx });
      setTimeout(fetchStatus, 300);
      showToast(`Встановлено: ${city}`);
    }

    function onLedAutoToggle(checked) {
      const el = document.getElementById('co2-thresholds-container');
      if (el) el.style.opacity = checked ? '1' : '0.4';
      autoSave({ led_auto: checked });
    }

    function detectJaamDistrict(lat, lon, admin2, admin1, cityName) {
      const sel = document.getElementById('sel-region');
      if (!sel) return 31;
      const opts = sel.options;

      const cLower = (cityName || '').toLowerCase().trim();
      if (cLower === 'київ' || cLower === 'м. київ' || cLower === 'kyiv' || cLower === 'kiev') {
        return 31;
      }

      // 1. Пріоритет: точний збіг назви міста з міською громадою ("м. <City> + ТГ")
      for (let i = 0; i < opts.length; i++) {
        const opt = opts[i];
        if (!opt.text.includes('+ ТГ') && !opt.text.includes('+ тг')) continue;
        const clean = opt.text.toLowerCase().replace('м. ', '').replace(' + тг', '').trim();
        const stem = clean.length > 5 ? clean.slice(0, -2) : (clean.length > 4 ? clean.slice(0, -1) : clean);
        if (cLower === clean || cLower === 'м. ' + clean || cLower.startsWith(clean + ' ') ||
            (cLower.includes('міська громада') && cLower.includes(stem))) {
          return parseInt(opt.value);
        }
      }

      // 2. Пошук за назвою району (admin2 або cityName)
      const target = ((admin2 || '') + ' ' + (cityName || '')).toLowerCase();
      for (let i = 0; i < opts.length; i++) {
        const opt = opts[i];
        if (parseInt(opt.value) === 31) continue;
        const isOblast = opt.text.includes('обл.') || opt.text.includes('Крим');
        if (isOblast) continue;
        const clean = opt.text.toLowerCase().replace(' район', '').replace('м. ', '').replace(' + тг', '').trim();
        const stem = clean.length > 5 ? clean.slice(0, -2) : clean;
        if (stem.length >= 3 && target.includes(stem)) {
          return parseInt(opt.value);
        }
      }

      // 3. Пошук найближчого районного центру за GPS-відстанню
      if (!isNaN(lat) && !isNaN(lon) && lat > 0 && lon > 0) {
        let bestDist = 1e9, bestId = -1;
        for (let i = 0; i < opts.length; i++) {
          const opt = opts[i];
          const isOblast = opt.text.includes('обл.') || opt.text.includes('Крим');
          if (isOblast) continue;
          const dlat = parseFloat(opt.getAttribute('data-lat')) || 0;
          const dlon = parseFloat(opt.getAttribute('data-lon')) || 0;
          if (dlat === 0 && dlon === 0) continue;
          const dy = dlat - lat;
          const dx = (dlon - lon) * Math.cos(lat * Math.PI / 180);
          const dist = dy * dy + dx * dx;
          if (dist < bestDist) {
            bestDist = dist;
            bestId = parseInt(opt.value);
          }
        }
        if (bestId > 0) return bestId;
      }

      // 4. Fallback до обласного рівня, якщо район не знайдено
      if (admin1) {
        const a1 = admin1.toLowerCase();
        for (let i = 0; i < opts.length; i++) {
          const opt = opts[i];
          if (opt.text.includes('обл.')) {
            const clean = opt.text.toLowerCase().replace(' обл.', '').trim();
            const stem = clean.length > 5 ? clean.slice(0, -2) : clean;
            if (stem.length >= 3 && a1.includes(stem)) {
              return parseInt(opt.value);
            }
          }
        }
      }

      return 31; // За замовчуванням м. Київ
    }

    async function autoDetectLocation() {
      setSaveStatus('saving', '⟳ Пошук IP...');
      showToast('Визначаємо геолокацію за IP...');
      try {
        let lat, lon, rawCity = '', regionName = '';
        try {
          const res = await fetch('https://ipapi.co/json/');
          if (res.ok) {
            const d = await res.json();
            lat = parseFloat(d.latitude);
            lon = parseFloat(d.longitude);
            rawCity = d.city || '';
            regionName = d.region || '';
          }
        } catch (e1) {}

        if (isNaN(lat) || isNaN(lon)) {
          const res2 = await fetch('https://get.geojs.io/v1/ip/geo.json');
          if (res2.ok) {
            const d2 = await res2.json();
            lat = parseFloat(d2.latitude);
            lon = parseFloat(d2.longitude);
            rawCity = d2.city || '';
            regionName = d2.region || '';
          }
        }

        if (isNaN(lat) || isNaN(lon)) throw new Error('Не вдалося визначити координати за IP');

        let finalCity = rawCity || 'Моє місто';
        let fullAdmin = regionName;
        let admin2 = '', admin1 = regionName;

        if (rawCity) {
          try {
            const places = await searchPlaces(rawCity);
            if (places && places.length > 0) {
              const r = places[0];
              finalCity = r.name;
              admin1 = r.admin1 || admin1;
              admin2 = r.admin2 || '';
              fullAdmin = [admin2, r.municipality, admin1].filter(Boolean).join(', ');
              if (!isNaN(parseFloat(r.latitude))) lat = parseFloat(r.latitude);
              if (!isNaN(parseFloat(r.longitude))) lon = parseFloat(r.longitude);
            }
          } catch (eGeo) {}
        }

        let regionIdx = detectJaamDistrict(lat, lon, admin2, admin1, finalCity);
        document.getElementById('inp-lat').value = lat.toFixed(4);
        document.getElementById('inp-lon').value = lon.toFixed(4);
        document.getElementById('sel-region').value = regionIdx;

        updateLocationDisplay(finalCity, regionIdx, lat, lon, fullAdmin);

        const patch = { lat, lon, city: finalCity, region: regionIdx };
        await autoSave(patch);
        setTimeout(fetchStatus, 300);
        showToast(`Встановлено: ${finalCity} (${fullAdmin || 'Україна'})`);
      } catch (err) {
        setSaveStatus('error', '⚠ Помилка локації');
        showToast('Не вдалося визначити локацію за IP');
      }
    }

    function onCustomCoordsChange() {
      const lat = parseFloat(document.getElementById('inp-lat').value) || 50.45;
      const lon = parseFloat(document.getElementById('inp-lon').value) || 30.52;
      const city = 'Користувацьке';
      const regionIdx = detectJaamDistrict(lat, lon, '', '', '');
      document.getElementById('sel-region').value = regionIdx;
      updateLocationDisplay(city, regionIdx, lat, lon, 'Ручні координати');
      autoSave({ lat, lon, city, region: regionIdx });
      setTimeout(fetchStatus, 300);
    }

    function showToast(msg) {
      const t = document.getElementById('toast');
      t.textContent = msg;
      t.classList.add('show');
      setTimeout(() => t.classList.remove('show'), 3000);
    }

    async function fetchStatus() {
      try {
        const res = await fetch('/api/status');
        if (!res.ok) return;
        const d = await res.json();
        currentSettings = d;

        // Sensors
        document.getElementById('val-co2').textContent = d.co2 != null ? d.co2 : '--';
        const co2El = document.getElementById('val-co2');
        const yThresh = (currentSettings.co2_yellow != null) ? currentSettings.co2_yellow : 1000;
        const rThresh = (currentSettings.co2_red != null) ? currentSettings.co2_red : 1500;
        if (d.co2 < yThresh) co2El.style.color = '#22c55e';
        else if (d.co2 < rThresh) co2El.style.color = '#f59e0b';
        else co2El.style.color = '#ef4444';

        document.getElementById('val-temp').textContent = d.temp != null ? d.temp.toFixed(1) : '--';
        document.getElementById('val-hum').textContent = d.hum != null ? d.hum.toFixed(0) : '--';
        
        if (d.usb) {
          document.getElementById('val-batt').textContent = 'USB';
          document.getElementById('val-batt-sub').textContent = 'живлення';
        } else {
          document.getElementById('val-batt').textContent = d.batt_pct != null ? d.batt_pct.toFixed(0) : '--';
          document.getElementById('val-batt-sub').textContent = '%';
        }

        // Alert
        const alertBadge = document.getElementById('alert-status-badge');
        const alertBanner = document.getElementById('live-alert-banner');
        if (d.alert_active) {
          alertBadge.textContent = 'ТРИВОГА!';
          alertBadge.className = 'badge badge-alert';
          alertBanner.style.display = 'flex';
        } else {
          alertBadge.textContent = 'Відбій';
          alertBadge.className = 'badge badge-clear';
          alertBanner.style.display = 'none';
        }

        // Versions
        if (d.version) document.getElementById('lbl-version').textContent = d.version;
        if (d.gd32_version) document.getElementById('lbl-gd32-ver').textContent = d.gd32_version;
        if (d.ip) document.getElementById('lbl-ip').textContent = d.ip;
        if (d.wifi_ssid) {
          const curWifiEl = document.getElementById('lbl-wifi-current');
          if (curWifiEl) curWifiEl.textContent = d.wifi_ssid;
        }

        // Update banner
        if (d.new_version) {
          document.getElementById('update-banner').style.display = 'block';
          document.getElementById('update-text').textContent = 'Доступна нова версія: ' + d.new_version;
        } else if (d.version && !window._checkedGithubRelease) {
          window._checkedGithubRelease = true;
          checkGithubRelease(d.version, false);
        }

      } catch (e) {
        console.error('Fetch status error:', e);
      }
    }

    function isNewerVersion(latest, current) {
      if (!latest || !current) return false;
      const parse = v => String(v).replace(/^v/, '').split('.').map(x => parseInt(x, 10) || 0);
      const l = parse(latest);
      const c = parse(current);
      for (let i = 0; i < Math.max(l.length, c.length); i++) {
        const lp = l[i] || 0;
        const cp = c[i] || 0;
        if (lp > cp) return true;
        if (lp < cp) return false;
      }
      return false;
    }

    async function checkGithubRelease(currentVer, showFeedback = false) {
      try {
        const resp = await fetch('https://api.github.com/repos/reidMaks/htram-esphome/releases/latest', {
          headers: { 'Accept': 'application/vnd.github.v3+json' }
        });
        if (!resp.ok) {
          if (showFeedback) showToast('Не вдалося перевірити GitHub');
          return;
        }
        const rel = await resp.json();
        const latestTag = rel.tag_name || '';
        if (latestTag && isNewerVersion(latestTag, currentVer)) {
          document.getElementById('update-banner').style.display = 'block';
          document.getElementById('update-text').textContent = 'Доступна нова версія: ' + latestTag;
          if (showFeedback) showToast('Знайдено нову версію ' + latestTag);
        } else if (showFeedback) {
          showToast('У вас встановлено найновішу версію');
        }
      } catch (err) {
        if (showFeedback) showToast('Помилка перевірки оновлень');
      }
    }

    function getSelectedAlarmDays() {
      const days = [];
      for (let d = 1; d <= 7; d++) {
        const el = document.getElementById('chk-day-' + d);
        if (el && el.checked) days.push(d);
      }
      return days;
    }

    function onAlarmDaysChange() {
      const days = getSelectedAlarmDays();
      autoSave({ alarm_days: days });
    }

    async function loadInitialSettings() {
      await fetchStatus();
      if (currentSettings.region != null) {
        document.getElementById('sel-region').value = currentSettings.region;
      }
      if (currentSettings.lat != null) document.getElementById('inp-lat').value = Number(currentSettings.lat).toFixed(4);
      if (currentSettings.lon != null) document.getElementById('inp-lon').value = Number(currentSettings.lon).toFixed(4);
      updateLocationDisplay(currentSettings.city, currentSettings.region, currentSettings.lat, currentSettings.lon);
      if (currentSettings.alarm_enabled != null) document.getElementById('chk-alarm').checked = currentSettings.alarm_enabled;
      if (currentSettings.alarm_time) document.getElementById('inp-alarm-time').value = currentSettings.alarm_time;
      if (currentSettings.alarm_days != null) {
        const days = currentSettings.alarm_days;
        for (let d = 1; d <= 7; d++) {
          const el = document.getElementById('chk-day-' + d);
          if (el) {
            if (Array.isArray(days)) {
              el.checked = days.includes(d);
            } else if (typeof days === 'number') {
              el.checked = Boolean(days & (1 << (d - 1)));
            }
          }
        }
      } else {
        for (let d = 1; d <= 7; d++) {
          const el = document.getElementById('chk-day-' + d);
          if (el) el.checked = true;
        }
      }
      if (currentSettings.silence_enabled != null) document.getElementById('chk-silence').checked = currentSettings.silence_enabled;
      if (currentSettings.brightness != null) {
        document.getElementById('rng-brightness').value = currentSettings.brightness;
        document.getElementById('lbl-brightness').textContent = currentSettings.brightness;
      }
      if (currentSettings.led_auto != null) {
        document.getElementById('chk-led-auto').checked = currentSettings.led_auto;
        const el = document.getElementById('co2-thresholds-container');
        if (el) el.style.opacity = currentSettings.led_auto ? '1' : '0.4';
      }
      if (currentSettings.co2_yellow != null) document.getElementById('inp-co2-yellow').value = currentSettings.co2_yellow;
      if (currentSettings.co2_red != null) document.getElementById('inp-co2-red').value = currentSettings.co2_red;
      if (currentSettings.temp_trim != null) document.getElementById('inp-trim').value = currentSettings.temp_trim;
      if (currentSettings.wifi_ssid) {
        const curWifiEl = document.getElementById('lbl-wifi-current');
        if (curWifiEl) curWifiEl.textContent = currentSettings.wifi_ssid;
      }
    }

    async function checkUpdates() {
      showToast('Перевірка оновлень...');
      try {
        const res = await fetch('/api/check_update', { method: 'POST' });
        const d = await res.json();
        if (d.new_version) {
          document.getElementById('update-banner').style.display = 'block';
          document.getElementById('update-text').textContent = 'Доступна нова версія: ' + d.new_version;
          showToast('Знайдено нову версію ' + d.new_version);
          return;
        }
        const cur = d.current_version || currentSettings.version || document.getElementById('lbl-version').textContent;
        await checkGithubRelease(cur, true);
      } catch (e) {
        const cur = currentSettings.version || document.getElementById('lbl-version').textContent;
        await checkGithubRelease(cur, true);
      }
    }

    async function triggerOtaUpdate() {
      if (!currentSettings.usb) {
        if (!confirm('Увага: пристрій працює від батареї!\nДля безпечного оновлення GD32 рекомендується підключити USB-живлення.\nПродовжити оновлення на батареї?')) return;
      } else {
        if (!confirm('Почати оновлення прошивки (GD32, асети, ESP32)? Пристрій перезавантажиться.')) return;
      }
      try {
        const url = !currentSettings.usb ? '/api/ota_update?on_battery=1' : '/api/ota_update';
        await fetch(url, { method: 'POST' });
        showToast('Оновлення розпочато (GD32, асети, ESP32). Зачекайте 1-2 хвилини...');
      } catch (e) {
        showToast('Не вдалося запустити оновлення');
      }
    }

    async function rebootDevice() {
      if (!confirm('Перезавантажити пристрій?')) return;
      try {
        await fetch('/api/reboot', { method: 'POST' });
        showToast('Пристрій перезавантажується...');
      } catch (e) {
        showToast('Помилка запиту перезавантаження');
      }
    }

    function toggleWifiPassVisibility() {
      const inp = document.getElementById('inp-wifi-pass');
      if (inp) {
        inp.type = inp.type === 'password' ? 'text' : 'password';
      }
    }

    async function saveWifiSettings() {
      const ssidEl = document.getElementById('inp-wifi-ssid');
      const passEl = document.getElementById('inp-wifi-pass');
      const ssid = ssidEl ? ssidEl.value.trim() : '';
      const password = passEl ? passEl.value : '';

      if (!ssid) {
        alert('Будь ласка, введіть назву мережі (SSID)');
        if (ssidEl) ssidEl.focus();
        return;
      }

      if (!confirm(`Зберегти Wi-Fi мережу "${ssid}" та перезавантажити годинник?\n\nЗв'язок за поточною IP-адресою буде розірвано.`)) {
        return;
      }

      showToast('Збереження Wi-Fi та перезавантаження...');
      try {
        const res = await fetch('/api/wifi', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ssid, password })
        });
        if (res.ok) {
          alert(`Параметри Wi-Fi збережено! Годинник перезавантажується.\n\n• Якщо дані вірні: підключіться до "${ssid}" та відкрийте http://htram.local\n• Якщо дані невірні: зачекайте точку доступу "HTRAM Setup" або натисніть кнопку 4 рази.`);
        } else {
          showToast('Помилка збереження Wi-Fi');
        }
      } catch (e) {
        showToast('Помилка надсилання запиту');
      }
    }

    document.addEventListener('click', (e) => {
      const searchBox = document.querySelector('.search-container');
      if (searchBox && !searchBox.contains(e.target)) {
        const dd = document.getElementById('city-search-results');
        if (dd) dd.classList.remove('show');
      }
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        const dd = document.getElementById('city-search-results');
        if (dd) dd.classList.remove('show');
      }
    });

    window.addEventListener('DOMContentLoaded', () => {
      loadInitialSettings();
      setInterval(fetchStatus, 4000);
    });
  </script>
</body>
</html>
)rawliteral";

}  // namespace htram_web
}  // namespace esphome
