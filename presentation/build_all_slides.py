# -*- coding: utf-8 -*-
"""Master HTML presentation builder for PEA One Agent."""

import os
import sys

import slides_sec0
import slides_sec1
import slides_sec2
import slides_sec3
import slides_sec4
import slides_sec5
import slides_sec6

OUTPUT_FILE = "pea_one_agent_presentation.html"

SECTIONS = [
    {"index": 0, "name": "ภาพรวม", "title": "ภาพรวมโครงการ", "start": 1, "end": 2},
    {"index": 1, "name": "ปัญหา SLA", "title": "ปัญหาและต้นเหตุ", "start": 3, "end": 7},
    {"index": 2, "name": "แนวคิด AI", "title": "แนวคิด Agentic AI", "start": 8, "end": 11},
    {"index": 3, "name": "สถาปัตยกรรม", "title": "สถาปัตยกรรม & เทคโนโลยี", "start": 12, "end": 21},
    {"index": 4, "name": "ปลั๊กอิน", "title": "ช่องทาง & ปลั๊กอิน", "start": 22, "end": 33},
    {"index": 5, "name": "เดโมจริง", "title": "ตัวอย่างการทำงานจริง", "start": 34, "end": 36},
    {"index": 6, "name": "ผลลัพธ์ ROI", "title": "ผลลัพธ์และแผนต่อไป", "start": 37, "end": 43},
]

CSS_STYLES = """
:root {
  --pea-purple: #6B3FA0;
  --pea-purple-dark: #4A2574;
  --pea-purple-deep: #2F134D;
  --pea-purple-light: #F4EFFB;
  --pea-purple-border: #E2D9F3;
  --pea-accent: #8E54E9;
  --status-red: #A6373A;
  --status-red-bg: #FDE8E8;
  --status-red-border: #F7C6C6;
  --status-amber: #B8631E;
  --status-amber-bg: #FEF3EB;
  --status-amber-border: #FAD7BF;
  --status-green: #276B47;
  --status-green-bg: #EAF5EE;
  --status-green-border: #BEE3CC;
  --status-blue: #1D5DA6;
  --status-blue-bg: #EAF2FB;
  --text-main: #1D192B;
  --text-muted: #49454F;
  --text-subtle: #79747E;
  --bg-white: #FFFFFF;
  --bg-light-gray: #F9F9FC;
  --border-light: #E7E3EE;
  --font-heading: 'Kanit', sans-serif;
  --font-body: 'IBM Plex Sans Thai', sans-serif;
  --font-mono: 'IBM Plex Mono', monospace;
}

* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

html, body {
  width: 100vw;
  height: 100vh;
  background-color: #0E0A17;
  overflow: hidden;
  display: flex;
  justify-content: center;
  align-items: center;
  font-family: var(--font-body);
  color: var(--text-main);
  user-select: none;
  -webkit-font-smoothing: antialiased;
}

/* Fixed 16:9 Viewport Centered */
#stage {
  width: 1280px;
  height: 720px;
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%) scale(1);
  transform-origin: center center;
  overflow: hidden;
  background: var(--bg-white);
  box-shadow: 0 16px 50px rgba(0, 0, 0, 0.7);
  display: flex;
  flex-direction: column;
}

/* TOP NAVIGATION BAR */
.topbar {
  height: 52px;
  background: #FFFFFF;
  border-bottom: 1px solid var(--border-light);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  z-index: 100;
  flex-shrink: 0;
  gap: 8px;
}

.topbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.pea-logo-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: linear-gradient(135deg, var(--pea-purple), var(--pea-purple-dark));
  color: #FFFFFF;
  padding: 4px 10px;
  border-radius: 6px;
  font-family: var(--font-heading);
  font-weight: 600;
  font-size: 12.5px;
  letter-spacing: 0.5px;
  white-space: nowrap;
}

.pea-bolt-icon {
  width: 14px;
  height: 14px;
  fill: #FFFFFF;
  flex-shrink: 0;
}

.project-topic-sub {
  font-size: 11px;
  color: var(--text-muted);
  border-left: 1px solid var(--border-light);
  padding-left: 8px;
  white-space: nowrap;
}

/* SECTION TRACKER */
.section-tracker {
  display: flex;
  align-items: center;
  gap: 2px;
  background: var(--pea-purple-light);
  padding: 2px 4px;
  border-radius: 20px;
  border: 1px solid var(--pea-purple-border);
  flex-shrink: 0;
}

.sec-pill {
  font-size: 10px;
  font-weight: 500;
  padding: 3px 6px;
  border-radius: 12px;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;
}

.sec-pill:hover {
  color: var(--pea-purple);
  background: rgba(107, 63, 160, 0.08);
}

.sec-pill.active {
  background: var(--pea-purple);
  color: #FFFFFF;
  font-weight: 600;
  box-shadow: 0 2px 6px rgba(107, 63, 160, 0.3);
}

/* TOPBAR RIGHT */
.topbar-right {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.rubric-tag {
  font-size: 10px;
  font-weight: 600;
  padding: 3px 7px;
  border-radius: 4px;
  background: var(--status-amber-bg);
  color: var(--status-amber);
  border: 1px solid var(--status-amber-border);
  white-space: nowrap;
  max-width: 130px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.slide-counter {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  background: #F1F1F6;
  padding: 3px 7px;
  border-radius: 4px;
  white-space: nowrap;
}

.nav-btn {
  background: #FFFFFF;
  border: 1px solid var(--border-light);
  color: var(--text-main);
  padding: 3px 8px;
  border-radius: 5px;
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 3px;
  transition: all 0.15s ease;
  white-space: nowrap;
}

.nav-btn:hover {
  background: var(--pea-purple-light);
  border-color: var(--pea-purple);
  color: var(--pea-purple);
}

/* PROGRESS BAR */
.progress-bar-track {
  height: 3px;
  background: #EAE6F2;
  width: 100%;
  flex-shrink: 0;
}

.progress-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--pea-purple), var(--pea-accent));
  width: 2.3%;
  transition: width 0.3s ease;
}

/* SLIDE CONTAINER & SLIDES */
.slides-viewport {
  flex: 1;
  position: relative;
  overflow: hidden;
}

.slide {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  display: none;
  flex-direction: column;
  padding: 22px 36px;
  background: var(--bg-white);
  overflow: hidden;
}

.slide.active {
  display: flex;
}

/* DARK THEME SLIDES */
.slide[data-theme="dark"] {
  background: radial-gradient(circle at 80% 20%, #431E6D 0%, var(--pea-purple-deep) 100%);
  color: #FFFFFF;
}

.slide[data-theme="dark"] .slide-header h2 {
  color: #FFFFFF;
}

.slide[data-theme="dark"] .slide-header .slide-subtitle {
  color: #DDD4ED;
}

/* SLIDE HEADER */
.slide-header {
  margin-bottom: 14px;
  flex-shrink: 0;
}

.slide-header h2 {
  font-family: var(--font-heading);
  font-size: 26px;
  font-weight: 600;
  color: var(--pea-purple-dark);
  line-height: 1.25;
  margin-bottom: 4px;
}

.slide-subtitle {
  font-size: 14px;
  color: var(--text-muted);
  line-height: 1.4;
}

.slide-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  justify-content: flex-start;
}

/* GENERAL UI COMPONENTS */
.badge {
  display: inline-flex;
  align-items: center;
  font-size: 11px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 4px;
}

.badge-purple { background: var(--pea-purple-light); color: var(--pea-purple); border: 1px solid var(--pea-purple-border); }
.badge-purple-glow { background: rgba(142, 84, 233, 0.25); color: #E8DEFA; border: 1px solid rgba(142, 84, 233, 0.6); }
.badge-outline-light { background: transparent; color: #FFFFFF; border: 1px solid rgba(255, 255, 255, 0.4); }
.badge-green-glow { background: rgba(39, 107, 71, 0.3); color: #9AE6B4; border: 1px solid #276B47; }
.badge-green { background: var(--status-green-bg); color: var(--status-green); border: 1px solid var(--status-green-border); }
.badge-amber { background: var(--status-amber-bg); color: var(--status-amber); border: 1px solid var(--status-amber-border); }
.badge-red { background: var(--status-red-bg); color: var(--status-red); border: 1px solid var(--status-red-border); }
.badge-blue { background: var(--status-blue-bg); color: var(--status-blue); border: 1px solid #B6D4F7; }

.status-pill {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 7px;
  border-radius: 12px;
  display: inline-block;
}
.status-fail { background: var(--status-red-bg); color: var(--status-red); border: 1px solid var(--status-red-border); }
.status-pass { background: var(--status-green-bg); color: var(--status-green); border: 1px solid var(--status-green-border); }
.status-amber { background: var(--status-amber-bg); color: var(--status-amber); border: 1px solid var(--status-amber-border); }
.status-neutral { background: #EEE; color: #555; }

.tag {
  font-size: 11px;
  background: #F0EDF5;
  color: var(--pea-purple);
  padding: 2px 6px;
  border-radius: 3px;
  font-family: var(--font-mono);
}

/* COVER SLIDE */
.cover-container {
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.cover-badge-row {
  display: flex;
  gap: 12px;
}

.cover-hero {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  margin: 10px 0;
}

.cover-logo-bolt {
  background: rgba(255, 255, 255, 0.1);
  width: 90px;
  height: 90px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 12px;
  border: 2px solid rgba(255, 255, 255, 0.25);
  box-shadow: 0 0 30px rgba(142, 84, 233, 0.5);
}

.cover-title {
  font-family: var(--font-heading);
  font-size: 48px;
  font-weight: 700;
  letter-spacing: 2px;
  color: #FFFFFF;
  text-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
}

.cover-tagline {
  font-size: 18px;
  color: #E2D9F3;
  max-width: 820px;
  line-height: 1.5;
  margin-top: 6px;
}

.cover-highlights-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin: 10px 0;
}

.highlight-card.dark-card {
  background: rgba(255, 255, 255, 0.07);
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 10px;
  padding: 14px;
  backdrop-filter: blur(8px);
}

.highlight-card .card-icon {
  font-size: 24px;
  margin-bottom: 8px;
}

.highlight-card h4 {
  font-family: var(--font-heading);
  font-size: 14px;
  color: #FFFFFF;
  margin-bottom: 4px;
}

.highlight-card p {
  font-size: 12px;
  color: #D3C9E3;
  line-height: 1.35;
}

.cover-footer-meta {
  display: flex;
  justify-content: space-between;
  border-top: 1px solid rgba(255, 255, 255, 0.15);
  padding-top: 12px;
  font-size: 12px;
  color: #BDB4CE;
}

.mono-text {
  font-family: var(--font-mono);
}

/* AGENDA GRID */
.agenda-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  height: 100%;
}

.agenda-card {
  background: var(--bg-light-gray);
  border: 1px solid var(--border-light);
  border-radius: 10px;
  padding: 16px;
  display: flex;
  gap: 14px;
  transition: transform 0.2s ease, border-color 0.2s ease;
}

.agenda-card:hover {
  border-color: var(--pea-purple);
  transform: translateY(-2px);
}

.agenda-num {
  font-family: var(--font-heading);
  font-size: 28px;
  font-weight: 700;
  color: var(--pea-purple);
  opacity: 0.8;
  line-height: 1;
}

.agenda-content {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.agenda-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.agenda-title {
  font-family: var(--font-heading);
  font-size: 16px;
  font-weight: 600;
  color: var(--text-main);
}

.agenda-desc {
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.4;
  margin-bottom: 10px;
  flex: 1;
}

.agenda-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

/* SECTION 1: ROOT CAUSE STYLES */
.three-cards-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 18px;
  margin-bottom: 14px;
}

.stat-card {
  background: #FFFFFF;
  border: 1px solid var(--border-light);
  border-radius: 10px;
  padding: 18px;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.03);
}

.border-left-purple { border-left: 4px solid var(--pea-purple); }
.border-left-amber { border-left: 4px solid var(--status-amber); }
.border-left-red { border-left: 4px solid var(--status-red); }

.card-badge {
  font-size: 11px;
  font-weight: 600;
  color: var(--pea-purple);
  margin-bottom: 6px;
}

.card-heading {
  font-family: var(--font-heading);
  font-size: 18px;
  font-weight: 600;
  color: var(--text-main);
  margin-bottom: 8px;
}

.card-desc {
  font-size: 13px;
  color: var(--text-muted);
  line-height: 1.45;
  margin-bottom: 12px;
}

.mini-tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.callout-box {
  background: var(--bg-light-gray);
  border: 1px solid var(--border-light);
  border-radius: 8px;
  padding: 12px 16px;
  display: flex;
  align-items: center;
  gap: 12px;
}

.amber-callout {
  background: var(--status-amber-bg);
  border-color: var(--status-amber-border);
}

.callout-icon {
  font-size: 20px;
}

.callout-text {
  font-size: 13px;
  color: #693208;
  line-height: 1.4;
}

/* SLA METRICS (SLIDE 4) */
.metric-cards-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}

.metric-box {
  background: #FFFFFF;
  border: 1px solid var(--border-light);
  border-radius: 10px;
  padding: 16px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.04);
}

.metric-box.alert-red {
  background: #FFF8F8;
  border: 1px solid var(--status-red-border);
  border-top: 4px solid var(--status-red);
}

.metric-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.metric-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-muted);
}

.metric-big-num {
  font-family: var(--font-heading);
  font-size: 38px;
  font-weight: 700;
  color: var(--status-red);
  line-height: 1.1;
  margin-bottom: 4px;
}

.metric-sub {
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 8px;
}

.metric-footer {
  font-size: 12px;
  color: #7E2729;
  border-top: 1px dashed var(--status-red-border);
  padding-top: 6px;
}

.sla-insight-row {
  display: grid;
  grid-template-columns: 1.4fr 1fr;
  gap: 16px;
}

.talktime-card {
  background: #FFFFFF;
  border: 1px solid var(--border-light);
  border-radius: 10px;
  padding: 14px 18px;
}

.talktime-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.talktime-header h4 {
  font-family: var(--font-heading);
  font-size: 14px;
  color: var(--text-main);
}

.talktime-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.tt-item {
  font-size: 12px;
  background: var(--bg-light-gray);
  padding: 6px 10px;
  border-radius: 6px;
  display: flex;
  justify-content: space-between;
}

.tt-label { color: var(--text-muted); }
.tt-val { font-weight: 600; font-family: var(--font-mono); }
.tt-target { color: var(--status-green); font-size: 11px; }

.core-insight-card {
  background: var(--pea-purple-light);
  border: 1px solid var(--pea-purple-border);
  border-radius: 10px;
  padding: 14px 18px;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.insight-badge {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.5px;
  color: var(--pea-purple);
  margin-bottom: 6px;
}

.insight-text {
  font-size: 13px;
  color: var(--pea-purple-dark);
  line-height: 1.5;
}

/* TWO COL CHARTS (SLIDE 5) */
.two-col-charts-container {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 12px;
}

.chart-panel {
  background: #FFFFFF;
  border: 1px solid var(--border-light);
  border-radius: 10px;
  padding: 14px 18px;
}

.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
}

.chart-header h4 {
  font-family: var(--font-heading);
  font-size: 14px;
  color: var(--text-main);
}

.custom-bar-chart {
  display: flex;
  justify-content: space-around;
  align-items: flex-end;
  height: 130px;
  padding-bottom: 8px;
  border-bottom: 1px solid #E0E0E0;
}

.bar-col {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  width: 44px;
}

.bar-val {
  font-size: 11px;
  font-family: var(--font-mono);
  font-weight: 600;
  color: var(--text-muted);
}

.bar-fill {
  width: 32px;
  background: #C4B0E0;
  border-radius: 4px 4px 0 0;
  transition: height 0.5s ease;
}

.bar-col.active-col .bar-fill {
  background: var(--pea-purple);
}

.red-bars .bar-fill {
  background: #F7B5B7;
}

.red-bars .bar-col.active-col-red .bar-fill {
  background: var(--status-red);
}

.bar-lbl {
  font-size: 11px;
  color: var(--text-subtle);
  margin-top: 4px;
}

.chart-note {
  font-size: 11px;
  color: var(--text-muted);
  text-align: center;
  margin-top: 8px;
}

.supporting-stats-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.sub-stat-box {
  background: var(--bg-light-gray);
  border: 1px solid var(--border-light);
  border-radius: 8px;
  padding: 10px 14px;
}

.sub-stat-num {
  font-family: var(--font-heading);
  font-size: 16px;
  font-weight: 700;
  color: var(--pea-purple-dark);
  margin-bottom: 2px;
}

.sub-stat-label {
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.35;
}

/* ROOT CAUSE 3 (SLIDE 6) */
.rootcause3-container {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.hourly-chart-wrapper {
  background: #FFFFFF;
  border: 1px solid var(--border-light);
  border-radius: 10px;
  padding: 14px 18px;
}

.chart-title-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.chart-title-row h4 {
  font-family: var(--font-heading);
  font-size: 14px;
}

.hourly-visual-strip {
  display: flex;
  height: 52px;
  border-radius: 6px;
  overflow: hidden;
  border: 1px solid var(--border-light);
}

.hour-block.offpeak {
  background: #F0EFF4;
  width: 10%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  color: var(--text-subtle);
}

.hour-block.peak-highlight {
  background: #FEF3EB;
  border-left: 2px dashed var(--status-amber);
  border-right: 2px dashed var(--status-amber);
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 0 12px;
}

.peak-badge-overlay {
  font-size: 12px;
  font-weight: 700;
  color: var(--status-amber);
  text-align: center;
  margin-bottom: 2px;
}

.peak-sub-hours {
  display: flex;
  justify-content: space-between;
  font-size: 10px;
  font-family: var(--font-mono);
  color: #8C470E;
}

.hourly-legend {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 6px;
}

.txt-amber { color: var(--status-amber); font-weight: 600; }

.strategy-comparison-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.strategy-card {
  border-radius: 10px;
  padding: 14px 18px;
}

.manual-trap {
  background: #FFF9F9;
  border: 1px solid var(--status-red-border);
}

.agentic-solution {
  background: var(--pea-purple-light);
  border: 1px solid var(--pea-purple-border);
}

.strategy-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.strategy-header h4 {
  font-family: var(--font-heading);
  font-size: 14px;
}

.strategy-list {
  list-style: none;
  font-size: 12px;
  line-height: 1.5;
}

.strategy-list li {
  margin-bottom: 6px;
}

/* TRANSITION SLIDES */
.transition-container {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.transition-card {
  text-align: center;
  max-width: 900px;
}

.transition-icon-large {
  margin-bottom: 14px;
}

.transition-title {
  font-family: var(--font-heading);
  font-size: 32px;
  font-weight: 700;
  color: #FFFFFF;
  margin-bottom: 12px;
}

.transition-quote {
  font-size: 16px;
  color: #D9CEEC;
  line-height: 1.6;
  margin-bottom: 24px;
}

.transition-arrow-box {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 20px;
  background: rgba(255, 255, 255, 0.08);
  padding: 16px 24px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.15);
}

.arrow-item {
  flex: 1;
  text-align: left;
}

.arrow-tag {
  font-size: 11px;
  color: #C0B4D6;
  margin-bottom: 4px;
}

.arrow-title {
  font-family: var(--font-heading);
  font-size: 15px;
  font-weight: 600;
  color: #FFFFFF;
  margin-bottom: 2px;
}

.arrow-sub {
  font-size: 12px;
  color: #BDB2D1;
}

.arrow-divider {
  font-size: 24px;
  color: var(--pea-accent);
}

/* TABLES (CONSULTING GRADE) */
.comparison-table-wrapper, .tech-table-wrapper {
  background: #FFFFFF;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  overflow: hidden;
}

.consulting-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12.5px;
  text-align: left;
}

.consulting-table th {
  background: var(--pea-purple-light);
  color: var(--pea-purple-dark);
  font-family: var(--font-heading);
  font-weight: 600;
  padding: 10px 14px;
  border-bottom: 1px solid var(--pea-purple-border);
}

.consulting-table td {
  padding: 9px 14px;
  border-bottom: 1px solid #F0EEF5;
  color: var(--text-main);
  line-height: 1.35;
}

.consulting-table tr:last-child td {
  border-bottom: none;
}

.consulting-table .col-highlight {
  background: #FAF7FD;
  border-left: 2px solid var(--pea-purple-border);
  color: var(--pea-purple-dark);
}

.consulting-table tr.row-spotlight td {
  background: #F5EDFD;
  font-weight: 500;
  border-top: 1px solid var(--pea-purple-border);
  border-bottom: 1px solid var(--pea-purple-border);
}

.consulting-table code {
  font-family: var(--font-mono);
  background: #EDE8F5;
  color: var(--pea-purple);
  padding: 2px 5px;
  border-radius: 3px;
  font-size: 11.5px;
}

/* STAIRCASE DESIGN PRINCIPLES (SLIDE 9) */
.principles-container {
  display: grid;
  grid-template-columns: 1.3fr 1fr;
  gap: 20px;
  align-items: center;
}

.staircase-wrapper {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.stair-step {
  display: flex;
  align-items: center;
  gap: 12px;
  background: var(--bg-light-gray);
  border: 1px solid var(--border-light);
  border-radius: 6px;
  padding: 7px 12px;
  transition: transform 0.2s ease;
}

.stair-step.step-1 {
  background: var(--pea-purple-light);
  border-color: var(--pea-purple);
  border-left: 5px solid var(--pea-purple);
  box-shadow: 0 2px 8px rgba(107, 63, 160, 0.15);
}

.stair-step .step-num {
  font-family: var(--font-mono);
  font-weight: 700;
  font-size: 13px;
  color: var(--pea-purple);
}

.stair-step .step-content {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.stair-step .step-content strong {
  font-size: 13px;
  color: var(--text-main);
}

.stair-step .step-content span {
  font-size: 11px;
  color: var(--text-muted);
}

.stair-step .step-badge {
  font-size: 10px;
  background: var(--pea-purple);
  color: #FFF;
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: 600;
}

.principles-quote-box {
  background: #FAF8FE;
  border: 1px solid var(--pea-purple-border);
  border-radius: 10px;
  padding: 20px;
}

.p-quote-header {
  font-size: 11px;
  font-weight: 700;
  color: var(--pea-purple);
  letter-spacing: 0.5px;
  margin-bottom: 10px;
}

.p-quote-text {
  font-size: 14px;
  color: var(--text-main);
  line-height: 1.6;
  margin-bottom: 12px;
}

.p-quote-meta {
  font-size: 11px;
  color: var(--text-subtle);
  font-family: var(--font-mono);
}

/* TOPOLOGY DIAGRAM (SLIDE 13) */
.topology-container {
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.layers-stack {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.topo-layer {
  background: #FFFFFF;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  padding: 8px 14px;
  display: flex;
  align-items: center;
  gap: 16px;
}

.layer-badge {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 700;
  width: 220px;
  color: var(--pea-purple);
  background: var(--pea-purple-light);
  padding: 4px 8px;
  border-radius: 4px;
  text-align: center;
}

.layer-items {
  display: flex;
  gap: 10px;
  flex: 1;
}

.layer-node {
  background: var(--bg-light-gray);
  border: 1px solid #DFDCED;
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  flex: 1;
  text-align: center;
}

.layer-node.highlight-node {
  background: #F3EDFA;
  border-color: var(--pea-purple);
  color: var(--pea-purple-dark);
}

.layer-node.dormant {
  opacity: 0.5;
  border-style: dashed;
}

.topo-arrow {
  text-align: center;
  font-size: 10px;
  color: #BDB4CE;
  line-height: 1;
}

/* CODE CARDS */
.code-card {
  background: #181424;
  border: 1px solid #332B45;
  border-radius: 8px;
  overflow: hidden;
  color: #E2DCF0;
  font-family: var(--font-mono);
}

.code-header {
  background: #251F33;
  padding: 6px 12px;
  font-size: 11px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: #B8B0CC;
  border-bottom: 1px solid #362D4A;
}

.code-tag {
  background: var(--pea-purple);
  color: #FFF;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 10px;
}

.code-block {
  padding: 12px 14px;
  font-size: 12px;
  line-height: 1.45;
  overflow-x: auto;
}

.code-footer {
  background: #211A2E;
  padding: 5px 12px;
  font-size: 11px;
  color: #9F97B6;
  border-top: 1px solid #302642;
}

.kw { color: #FF7B72; font-weight: 600; }
.cls { color: #79C0FF; font-weight: 600; }
.fn { color: #D2A8FF; font-weight: 600; }
.str { color: #A5D6FF; }
.val { color: #7EE787; }
.comment { color: #8B949E; font-style: italic; }
.yaml-key { color: #79C0FF; }

/* MAIN AGENT RULES (SLIDE 14) */
.main-agent-grid {
  display: grid;
  grid-template-columns: 1.1fr 1fr;
  gap: 16px;
}

.agent-rules-card {
  background: #FFFFFF;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  padding: 14px 18px;
}

.agent-rules-card h4 {
  font-family: var(--font-heading);
  font-size: 15px;
  color: var(--text-main);
  margin-bottom: 10px;
}

.rule-item {
  display: flex;
  gap: 10px;
  margin-bottom: 10px;
}

.rule-badge {
  background: var(--pea-purple);
  color: #FFF;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  flex-shrink: 0;
  margin-top: 2px;
}

.rule-item strong {
  font-size: 12.5px;
  color: var(--text-main);
}

.rule-item p {
  font-size: 11.5px;
  color: var(--text-muted);
  line-height: 1.35;
}

/* STATE MACHINE (SLIDE 19) */
.state-machine-container {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.state-flow-diagram {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--pea-purple-light);
  border: 1px solid var(--pea-purple-border);
  border-radius: 10px;
  padding: 16px 20px;
}

.flow-step-box {
  background: #FFFFFF;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  padding: 12px 14px;
  width: 220px;
  text-align: center;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.flow-step-box h4 {
  font-family: var(--font-mono);
  font-size: 15px;
  color: var(--pea-purple-dark);
  margin: 6px 0 4px 0;
}

.flow-step-box p {
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.3;
}

.flow-arrow {
  font-size: 20px;
  color: var(--pea-purple);
}

.safety-rules-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
}

.safety-rule-card {
  background: #FFFFFF;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  padding: 14px;
}

.safety-rule-card h4 {
  font-family: var(--font-heading);
  font-size: 14px;
  margin-bottom: 6px;
}

.safety-rule-card p {
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.4;
}

/* TERMINAL MOCKUP (SLIDE 31) */
.cli-demo-container {
  display: grid;
  grid-template-columns: 1.2fr 1fr;
  gap: 16px;
}

.terminal-window {
  background: #101016;
  border-radius: 8px;
  border: 1px solid #2B2836;
  overflow: hidden;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
}

.term-header {
  background: #1E1B29;
  padding: 6px 12px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  display: inline-block;
}
.dot.red { background: #FF5F56; }
.dot.yellow { background: #FFBD2E; }
.dot.green { background: #27C93F; }

.term-title {
  font-size: 11px;
  color: #9C94AD;
  margin-left: 8px;
  font-family: var(--font-mono);
}

.term-body {
  padding: 14px;
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 1.5;
  color: #D6D0E0;
}

.prompt-line { color: #6CE89A; font-weight: 600; margin-bottom: 6px; }
.success-line { color: #FFBD2E; }
.info-line { color: #A79CC2; }
.done-line { color: #6CE89A; margin-top: 8px; }

.cli-steps-card {
  background: #FFFFFF;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  padding: 14px 18px;
}

.cli-steps-card h4 {
  font-family: var(--font-heading);
  font-size: 15px;
  color: var(--pea-purple);
  margin-bottom: 10px;
}

.cs-step {
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 8px;
  line-height: 1.35;
}

/* HORIZONTAL BARS (SLIDE 37) */
.testing-stats-tiles {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 14px;
}

.test-stat-tile {
  background: #FFFFFF;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  padding: 10px 14px;
  text-align: center;
}

.test-stat-tile.tile-purple { border-top: 3px solid var(--pea-purple); }
.test-stat-tile.tile-green { border-top: 3px solid var(--status-green); }
.test-stat-tile.tile-blue { border-top: 3px solid var(--status-blue); }
.test-stat-tile.tile-amber { border-top: 3px solid var(--status-amber); }

.t-val {
  font-family: var(--font-heading);
  font-size: 24px;
  font-weight: 700;
  color: var(--text-main);
}

.t-lbl {
  font-size: 11px;
  color: var(--text-muted);
}

.test-breakdown-chart {
  background: #FFFFFF;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  padding: 14px 18px;
}

.test-breakdown-chart h4 {
  font-family: var(--font-heading);
  font-size: 13.5px;
  margin-bottom: 10px;
}

.hbar-grid {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.hbar-row {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 11px;
}

.hbar-name {
  width: 250px;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.hbar-track {
  flex: 1;
  height: 10px;
  background: #EEEBF2;
  border-radius: 5px;
  overflow: hidden;
}

.hbar-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--pea-purple), var(--pea-accent));
  border-radius: 5px;
}

.hbar-count {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  width: 60px;
  text-align: right;
  color: var(--pea-purple-dark);
}

/* ROI COMPARISON (SLIDE 39) */
.roi-cards-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
  margin-bottom: 14px;
}

.roi-metric-card {
  background: #FFFFFF;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  padding: 12px 16px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.03);
}

.roi-metric-card.highlight-green {
  border-top: 4px solid var(--status-green);
  background: #F8FCF9;
}

.roi-metric-card.highlight-purple {
  border-top: 4px solid var(--pea-purple);
  background: #FAF8FE;
}

.rmc-label {
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 4px;
}

.rmc-main-val {
  font-family: var(--font-heading);
  font-size: 28px;
  font-weight: 700;
  color: var(--text-main);
  line-height: 1.1;
  margin-bottom: 4px;
}

.highlight-green .rmc-main-val { color: var(--status-green); }
.highlight-purple .rmc-main-val { color: var(--pea-purple); }

.rmc-sub {
  font-size: 11.5px;
  color: var(--text-muted);
}

.cost-comparison-bars-wrapper {
  background: #FFFFFF;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  padding: 14px 18px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  margin-bottom: 12px;
}

.cb-col h4 {
  font-family: var(--font-heading);
  font-size: 13.5px;
  margin-bottom: 4px;
}

.cb-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.cb-bar-track {
  height: 24px;
  background: #EEEBF2;
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 6px;
}

.cb-bar-fill {
  height: 100%;
  background: var(--status-amber);
  color: #FFF;
  font-size: 11px;
  font-family: var(--font-mono);
  display: flex;
  align-items: center;
  padding-left: 10px;
  font-weight: 600;
}

.cb-bar-fill.fill-green {
  background: var(--status-green);
}

.cb-calc {
  font-size: 11px;
  color: var(--text-subtle);
  font-family: var(--font-mono);
}

.assumptions-box {
  background: var(--bg-light-gray);
  border: 1px solid var(--border-light);
  border-radius: 6px;
  padding: 10px 14px;
}

.as-title {
  font-size: 11px;
  font-weight: 700;
  color: var(--pea-purple);
  margin-bottom: 4px;
}

.as-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px 16px;
  font-size: 10.5px;
  color: var(--text-muted);
  line-height: 1.35;
}

/* CLOSING SLIDE (SLIDE 43) */
.closing-container {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.closing-card {
  text-align: center;
  max-width: 850px;
}

.closing-bolt {
  margin-bottom: 10px;
}

.closing-title {
  font-family: var(--font-heading);
  font-size: 42px;
  color: #FFFFFF;
  margin-bottom: 6px;
}

.closing-sub {
  font-size: 16px;
  color: #DDD4ED;
  margin-bottom: 24px;
}

.closing-three-pillars {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

.cp-item {
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 8px;
  padding: 16px;
}

.cp-num {
  font-family: var(--font-heading);
  font-size: 22px;
  font-weight: 700;
  color: #FFD166;
  margin-bottom: 6px;
}

.cp-txt {
  font-size: 12px;
  color: #D3C9E3;
  line-height: 1.4;
}

.closing-contact-row {
  border-top: 1px solid rgba(255, 255, 255, 0.15);
  padding-top: 16px;
}

.cc-badge {
  font-size: 14px;
  font-weight: 600;
  color: #FFFFFF;
  margin-bottom: 4px;
}

.cc-meta {
  font-size: 12px;
  color: #BDB4CE;
}

/* JUMP MODAL */
.modal-overlay {
  display: none;
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(14, 10, 23, 0.85);
  backdrop-filter: blur(5px);
  z-index: 200;
  align-items: center;
  justify-content: center;
}

.modal-overlay.open {
  display: flex;
}

.modal-window {
  width: 950px;
  height: 600px;
  background: #FFFFFF;
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.4);
  overflow: hidden;
}

.modal-header {
  padding: 14px 20px;
  background: var(--pea-purple-light);
  border-bottom: 1px solid var(--pea-purple-border);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.modal-header h3 {
  font-family: var(--font-heading);
  font-size: 18px;
  color: var(--pea-purple-dark);
}

.modal-close-btn {
  background: transparent;
  border: none;
  font-size: 20px;
  cursor: pointer;
  color: var(--text-muted);
}

.modal-body {
  flex: 1;
  padding: 16px 20px;
  overflow-y: auto;
}

.modal-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
}

.modal-slide-card {
  background: var(--bg-light-gray);
  border: 1px solid var(--border-light);
  border-radius: 6px;
  padding: 8px 10px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.modal-slide-card:hover {
  background: var(--pea-purple-light);
  border-color: var(--pea-purple);
}

.modal-slide-card.current {
  border-color: var(--pea-purple);
  background: #EDE6F7;
  font-weight: 600;
}

.m-slide-num {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--pea-purple);
  font-weight: 700;
}

.m-slide-title {
  font-size: 11px;
  color: var(--text-main);
  line-height: 1.3;
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* FLOW ARCHITECTURE (SLIDE 13) */
.flow-architecture-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  height: 100%;
}

.flow-image-card {
  position: relative;
  width: 100%;
  max-width: 1120px;
  height: 440px;
  background: #FFFFFF;
  border: 1px solid var(--border-light);
  border-radius: 10px;
  padding: 8px;
  box-shadow: 0 8px 24px rgba(107, 63, 160, 0.08);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
  overflow: hidden;
}

.flow-image-card:hover {
  box-shadow: 0 12px 32px rgba(107, 63, 160, 0.18);
  border-color: var(--pea-purple);
  transform: translateY(-2px);
}

.flow-hero-img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  border-radius: 6px;
}

.img-zoom-hint {
  position: absolute;
  bottom: 12px;
  right: 16px;
  background: rgba(47, 19, 77, 0.85);
  color: #FFFFFF;
  padding: 5px 14px;
  border-radius: 20px;
  font-size: 11px;
  font-weight: 500;
  backdrop-filter: blur(4px);
  pointer-events: none;
  box-shadow: 0 2px 8px rgba(0,0,0,0.3);
}

.arch-key-callouts {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  width: 100%;
  max-width: 1120px;
}

.ak-card {
  background: #FFFFFF;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  padding: 8px 12px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  box-shadow: 0 2px 6px rgba(0,0,0,0.03);
}

.ak-card.highlight-ak {
  border-color: var(--pea-purple);
  background: #FAF7FD;
}

.ak-title {
  font-family: var(--font-heading);
  font-size: 12px;
  font-weight: 600;
  color: var(--pea-purple-dark);
  display: flex;
  align-items: center;
  gap: 5px;
}

.ak-desc {
  font-size: 10.5px;
  color: var(--text-muted);
  line-height: 1.35;
}

/* LINE INTERFACE & RICH MENU (SLIDE 26) */
.line-interface-container {
  display: grid;
  grid-template-columns: 1fr 1.1fr;
  gap: 20px;
  height: 100%;
  align-items: start;
}

.line-mockup-wrapper {
  background: #FFFFFF;
  border: 1px solid var(--border-light);
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 8px 24px rgba(0,0,0,0.06);
}

.line-header {
  background: #06C755;
  color: #FFFFFF;
  padding: 8px 14px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-family: var(--font-heading);
  font-weight: 600;
  font-size: 13px;
}

.line-chat-flow {
  padding: 12px;
  background: #849EB5;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 220px;
}

.line-bubble {
  padding: 8px 12px;
  border-radius: 12px;
  font-size: 11.5px;
  line-height: 1.4;
  max-width: 85%;
}

.line-user {
  background: #FFFFFF;
  align-self: flex-end;
  border-bottom-right-radius: 2px;
  color: #111111;
}

.line-agent {
  background: #FFFFFF;
  align-self: flex-start;
  border-bottom-left-radius: 2px;
  color: #111111;
}

.line-postback-box {
  background: #FFFFFF;
  border-radius: 8px;
  padding: 10px;
  margin-top: 4px;
  border: 1px solid #DFDCED;
}

.postback-info {
  font-size: 11px;
  color: #333333;
  margin-bottom: 8px;
}

.postback-btn-row {
  display: flex;
  gap: 6px;
}

.line-btn {
  flex: 1;
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  border: none;
}

.btn-line-confirm {
  background: #06C755;
  color: #FFFFFF;
}

.btn-line-cancel {
  background: #EFEFEF;
  color: #666666;
}

.line-richmenu-preview {
  position: relative;
  cursor: pointer;
  border-top: 2px solid #06C755;
  background: #F8F9FA;
  overflow: hidden;
  transition: all 0.2s ease;
}

.line-richmenu-preview:hover {
  opacity: 0.95;
}

.line-richmenu-img {
  width: 100%;
  display: block;
  object-fit: cover;
  max-height: 160px;
}

.richmenu-caption {
  position: absolute;
  bottom: 6px;
  right: 8px;
  background: rgba(0,0,0,0.7);
  color: #FFFFFF;
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 10px;
}

.line-specs-card {
  background: #FFFFFF;
  border: 1px solid var(--border-light);
  border-radius: 10px;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.line-specs-card h4 {
  font-family: var(--font-heading);
  font-size: 15px;
  color: var(--pea-purple);
  margin-bottom: 4px;
}

.ls-item strong {
  font-size: 12px;
  color: var(--pea-purple-dark);
  display: block;
  margin-bottom: 2px;
}

.ls-item p {
  font-size: 11.5px;
  color: var(--text-muted);
  line-height: 1.4;
  margin: 0;
}

/* PILOT EVALUATION 2 UNITS (SLIDE 38) */
.pilot-evaluation-container {
  display: flex;
  flex-direction: column;
  gap: 10px;
  height: 100%;
}

.pilot-framework-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  flex: 1;
}

.pilot-unit-card {
  background: #FFFFFF;
  border: 1px solid var(--border-light);
  border-radius: 10px;
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  box-shadow: 0 4px 14px rgba(0,0,0,0.04);
}

.pilot-unit-card.unit-1 {
  border-top: 4px solid var(--pea-purple);
}

.pilot-unit-card.unit-2 {
  border-top: 4px solid #1D5DA6;
}

.p-card-header {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.p-badge {
  display: inline-block;
  font-size: 10.5px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 4px;
  width: fit-content;
}

.p-badge-purple {
  background: var(--pea-purple-light);
  color: var(--pea-purple);
  border: 1px solid var(--pea-purple-border);
}

.p-badge-blue {
  background: #EAF2FB;
  color: #1D5DA6;
  border: 1px solid #BFD9F5;
}

.p-unit-title {
  font-family: var(--font-heading);
  font-size: 14px;
  font-weight: 600;
  color: var(--text-main);
  padding: 2px 4px;
  border-radius: 4px;
  outline: none;
}

.p-unit-title:focus, .pf-editable:focus, .p-feedback-box p:focus, .highlight-col .pm-item:focus {
  background: #FFF9E6;
  box-shadow: 0 0 0 2px #F5A623;
}

.p-field-row {
  background: var(--bg-light-gray);
  border-radius: 6px;
  padding: 5px 8px;
  font-size: 10.5px;
}

.pf-label {
  font-weight: 600;
  color: var(--text-main);
  display: block;
  margin-bottom: 2px;
}

.pf-editable {
  color: var(--text-muted);
  line-height: 1.3;
  outline: none;
}

.p-metrics-table {
  display: grid;
  grid-template-columns: 1.2fr 1fr 1fr;
  background: #FAF9FD;
  border: 1px solid #E6E1F2;
  border-radius: 6px;
  overflow: hidden;
}

.pm-col {
  padding: 6px 8px;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.pm-col.highlight-col {
  background: #FFFFFF;
  border-left: 1px solid #E6E1F2;
  box-shadow: inset 0 0 8px rgba(107, 63, 160, 0.05);
}

.pm-lbl {
  font-size: 9.5px;
  font-weight: 700;
  color: var(--text-muted);
  text-transform: uppercase;
  margin-bottom: 2px;
  border-bottom: 1px solid #E6E1F2;
  padding-bottom: 3px;
}

.pm-item {
  font-size: 10.5px;
  font-family: var(--font-mono);
  outline: none;
}

.red-txt { color: var(--status-red); font-weight: 600; }
.green-txt { color: var(--status-green); font-weight: 700; }
.purple-txt { color: var(--pea-purple); font-weight: 700; }

.p-feedback-box {
  display: flex;
  gap: 8px;
  background: #FBF7FD;
  border: 1px solid var(--pea-purple-border);
  border-radius: 6px;
  padding: 6px 8px;
  align-items: flex-start;
}

.fb-icon {
  font-size: 15px;
  flex-shrink: 0;
}

.fb-content strong {
  font-size: 10.5px;
  color: var(--pea-purple-dark);
  display: block;
  margin-bottom: 2px;
}

.fb-content p {
  font-size: 10.5px;
  font-style: italic;
  color: #4A3E5C;
  line-height: 1.3;
  margin: 0;
  outline: none;
}

.pilot-bottom-strip {
  background: #FFFFFF;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  padding: 6px 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 11px;
}

.so-title {
  font-weight: 700;
  color: var(--pea-purple);
  margin-right: 6px;
}

.demo-link-badge code {
  background: var(--pea-purple-light);
  color: var(--pea-purple);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: var(--font-mono);
  font-weight: 600;
}

/* IMAGE LIGHTBOX ZOOM MODAL */
.image-modal-window {
  background: rgba(18, 14, 26, 0.96);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 12px;
  padding: 16px;
  max-width: 95vw;
  max-height: 92vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  position: relative;
  box-shadow: 0 24px 64px rgba(0, 0, 0, 0.85);
}

.image-modal-img {
  max-width: 92vw;
  max-height: 80vh;
  object-fit: contain;
  border-radius: 8px;
}

.image-modal-caption {
  font-family: var(--font-heading);
  color: #FFFFFF;
  font-size: 14px;
  font-weight: 600;
  margin-top: 10px;
  text-align: center;
}

.modal-close-btn {
  position: absolute;
  top: 12px;
  right: 14px;
  background: rgba(255, 255, 255, 0.15);
  border: 1px solid rgba(255, 255, 255, 0.3);
  color: #FFFFFF;
  padding: 4px 12px;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.modal-close-btn:hover {
  background: rgba(255, 255, 255, 0.3);
}
"""

JS_SCRIPTS = """
let currentSlide = 1;
const totalSlides = 43;

const sections = [
  { index: 0, name: "ภาพรวม", start: 1, end: 2 },
  { index: 1, name: "ปัญหา SLA", start: 3, end: 7 },
  { index: 2, name: "แนวคิด AI", start: 8, end: 11 },
  { index: 3, name: "สถาปัตยกรรม", start: 12, end: 21 },
  { index: 4, name: "ปลั๊กอิน", start: 22, end: 33 },
  { index: 5, name: "เดโมจริง", start: 34, end: 36 },
  { index: 6, name: "ผลลัพธ์ ROI", start: 37, end: 43 }
];

function rescale() {
  const stage = document.getElementById('stage');
  const scale = Math.min(window.innerWidth / 1280, window.innerHeight / 720);
  stage.style.transform = `translate(-50%, -50%) scale(${scale})`;
}

function showSlide(index) {
  if (index < 1) index = 1;
  if (index > totalSlides) index = totalSlides;
  currentSlide = index;

  // Deactivate old, activate new
  document.querySelectorAll('.slide').forEach(el => el.classList.remove('active'));
  const target = document.getElementById(`slide-${currentSlide}`);
  if (target) target.classList.add('active');

  // Update Topbar
  document.getElementById('slide-counter-text').innerText = `Slide ${currentSlide} / ${totalSlides}`;
  const progressPct = (currentSlide / totalSlides) * 100;
  document.getElementById('progress-bar').style.width = `${progressPct}%`;

  // Update Rubric Badge
  const rubric = target ? target.getAttribute('data-rubric') : '';
  const rubricEl = document.getElementById('rubric-badge');
  if (rubricEl) {
    let shortRubric = rubric;
    if (rubric.includes('เกณฑ์ A + C')) shortRubric = 'เกณฑ์ A+C (40 คะแนน)';
    else if (rubric.includes('เกณฑ์ A + B')) shortRubric = 'เกณฑ์ A+B (26 คะแนน)';
    else if (rubric.includes('เกณฑ์ A')) shortRubric = 'เกณฑ์ A (16 คะแนน)';
    else if (rubric.includes('เกณฑ์ B')) shortRubric = 'เกณฑ์ B (10 คะแนน)';
    else if (rubric.includes('เกณฑ์ C')) shortRubric = 'เกณฑ์ C (24 คะแนน)';
    else if (rubric.includes('ภาพรวม')) shortRubric = 'ภาพรวม';
    else if (rubric.includes('บทสรุป')) shortRubric = 'บทสรุป';
    rubricEl.innerText = shortRubric;
    rubricEl.title = rubric;
    if (rubric.includes('เกณฑ์ C')) {
      rubricEl.style.background = 'var(--status-green-bg)';
      rubricEl.style.color = 'var(--status-green)';
      rubricEl.style.borderColor = 'var(--status-green-border)';
    } else if (rubric.includes('เกณฑ์ B')) {
      rubricEl.style.background = 'var(--pea-purple-light)';
      rubricEl.style.color = 'var(--pea-purple)';
      rubricEl.style.borderColor = 'var(--pea-purple-border)';
    } else if (rubric.includes('เกณฑ์ A')) {
      rubricEl.style.background = 'var(--status-amber-bg)';
      rubricEl.style.color = 'var(--status-amber)';
      rubricEl.style.borderColor = 'var(--status-amber-border)';
    } else {
      rubricEl.style.background = '#F0EDF5';
      rubricEl.style.color = 'var(--pea-purple-dark)';
      rubricEl.style.borderColor = '#DDD6EB';
    }
  }

  // Update Section Tracker
  const curSec = sections.find(s => currentSlide >= s.start && currentSlide <= s.end);
  document.querySelectorAll('.sec-pill').forEach(pill => {
    const secIdx = parseInt(pill.getAttribute('data-section'), 10);
    if (curSec && curSec.index === secIdx) {
      pill.classList.add('active');
    } else {
      pill.classList.remove('active');
    }
  });

  // Update modal selection
  document.querySelectorAll('.modal-slide-card').forEach(c => {
    const sId = parseInt(c.getAttribute('data-slide-id'), 10);
    if (sId === currentSlide) c.classList.add('current');
    else c.classList.remove('current');
  });
}

function nextSlide() { showSlide(currentSlide + 1); }
function prevSlide() { showSlide(currentSlide - 1); }

function jumpToSection(secIndex) {
  const s = sections.find(sec => sec.index === secIndex);
  if (s) showSlide(s.start);
}

function toggleModal() {
  const modal = document.getElementById('jump-modal');
  modal.classList.toggle('open');
}

function openImageModal(src, caption) {
  const modal = document.getElementById('image-modal');
  const img = document.getElementById('image-modal-img');
  const cap = document.getElementById('image-modal-caption');
  if (modal && img) {
    img.src = src;
    if (cap) cap.innerText = caption || '';
    modal.classList.add('open');
  }
}

function closeImageModal() {
  const modal = document.getElementById('image-modal');
  if (modal) modal.classList.remove('open');
}

function toggleFullscreen() {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen().catch(() => {});
  } else {
    if (document.exitFullscreen) document.exitFullscreen();
  }
}

// Keyboard Listeners
window.addEventListener('keydown', (e) => {
  if (e.key === 'ArrowRight' || e.key === ' ' || e.key === 'PageDown' || e.key === 'j' || e.key === 'l') {
    nextSlide();
  } else if (e.key === 'ArrowLeft' || e.key === 'Backspace' || e.key === 'PageUp' || e.key === 'k' || e.key === 'h') {
    prevSlide();
  } else if (e.key === 'Home') {
    showSlide(1);
  } else if (e.key === 'End') {
    showSlide(totalSlides);
  } else if (e.key === 'f' || e.key === 'F') {
    toggleFullscreen();
  } else if (e.key === 'g' || e.key === 'G' || e.key === 'o' || e.key === 'O') {
    toggleModal();
  } else if (e.key === 'Escape') {
    const jumpModal = document.getElementById('jump-modal');
    if (jumpModal && jumpModal.classList.contains('open')) jumpModal.classList.remove('open');
    closeImageModal();
  }
});

window.addEventListener('resize', rescale);
window.addEventListener('DOMContentLoaded', () => {
  rescale();
  showSlide(1);
});
"""

def generate_html():
    all_slides = (
        slides_sec0.get_slides() +
        slides_sec1.get_slides() +
        slides_sec2.get_slides() +
        slides_sec3.get_slides() +
        slides_sec4.get_slides() +
        slides_sec5.get_slides() +
        slides_sec6.get_slides()
    )

    # Build Section buttons HTML
    sec_pills_html = "".join([
        f'<div class="sec-pill" data-section="{s["index"]}" onclick="jumpToSection({s["index"]})">{s["index"]}. {s["name"]}</div>'
        for s in SECTIONS
    ])

    # Build Slides HTML
    slides_html_list = []
    for s in all_slides:
        slide_html = f"""
<div class="slide" id="slide-{s['id']}" data-section="{s['section']}" data-rubric="{s['rubric']}" data-theme="{s['theme']}">
    <div class="slide-header">
        <h2>{s['title']}</h2>
        <div class="slide-subtitle">{s['subtitle']}</div>
    </div>
    <div class="slide-body">
        {s['content']}
    </div>
</div>
"""
        slides_html_list.append(slide_html)

    slides_rendered = "\n".join(slides_html_list)

    # Build Modal cards HTML
    modal_cards = []
    for s in all_slides:
        card = f"""
<div class="modal-slide-card" data-slide-id="{s['id']}" onclick="showSlide({s['id']}); toggleModal();">
    <div class="m-slide-num">SLIDE {s['id']:02d}</div>
    <div class="m-slide-title">{s['title']}</div>
</div>
"""
        modal_cards.append(card)
    modal_cards_html = "".join(modal_cards)

    full_html = f"""<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PEA One Agent — Presentation Deck</title>
    <!-- Google Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&family=IBM+Plex+Sans+Thai:wght@300;400;500;600;700&family=Kanit:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
{CSS_STYLES}
    </style>
</head>
<body>

<div id="stage">
    <!-- TOPBAR -->
    <div class="topbar">
        <div class="topbar-left">
            <div class="pea-logo-badge">
                <svg class="pea-bolt-icon" viewBox="0 0 24 24"><path d="M13.6 1.6 4.9 13.9h4.9L8.6 22.4l9.1-12.7h-5l.9-8.1z"/></svg>
                <span>PEA ONE AGENT</span>
            </div>
            <span class="project-topic-sub">หัวข้อ 3: Agentic AI</span>
        </div>

        <!-- SECTION TRACKER -->
        <div class="section-tracker">
            {sec_pills_html}
        </div>

        <!-- TOPBAR RIGHT -->
        <div class="topbar-right">
            <span class="rubric-tag" id="rubric-badge">ภาพรวมโครงการ</span>
            <span class="slide-counter" id="slide-counter-text">Slide 01 / 43</span>
            <button class="nav-btn" onclick="toggleModal()" title="สารบัญ (G / O)">⊞ สารบัญ</button>
            <button class="nav-btn" onclick="prevSlide()" title="ก่อนหน้า (Left / PageUp)">◀</button>
            <button class="nav-btn" onclick="nextSlide()" title="ถัดไป (Right / Space / PageDown)">▶</button>
            <button class="nav-btn" onclick="toggleFullscreen()" title="เต็มจอ (F)">⛶</button>
        </div>
    </div>

    <!-- PROGRESS BAR -->
    <div class="progress-bar-track">
        <div class="progress-bar-fill" id="progress-bar"></div>
    </div>

    <!-- SLIDES VIEWPORT -->
    <div class="slides-viewport">
        {slides_rendered}
    </div>

    <!-- JUMP MODAL -->
    <div class="modal-overlay" id="jump-modal" onclick="if(event.target === this) toggleModal();">
        <div class="modal-window">
            <div class="modal-header">
                <h3>สารบัญสไลด์ทั้งหมด (43 สไลด์) — คลิกเพื่อข้ามสไลด์</h3>
                <button class="modal-close-btn" onclick="toggleModal()">✕</button>
            </div>
            <div class="modal-body">
                <div class="modal-grid">
                    {modal_cards_html}
                </div>
            </div>
        </div>
    </div>

    <!-- IMAGE LIGHTBOX ZOOM MODAL -->
    <div class="modal-overlay" id="image-modal" onclick="closeImageModal()">
        <div class="image-modal-window" onclick="event.stopPropagation()">
            <button class="modal-close-btn" onclick="closeImageModal()">✕ ปิด</button>
            <img id="image-modal-img" class="image-modal-img" src="" alt="Enlarged Diagram">
            <div id="image-modal-caption" class="image-modal-caption"></div>
        </div>
    </div>
</div>

<script>
{JS_SCRIPTS}
</script>
</body>
</html>
"""

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(full_html)

    print(f"Successfully generated {OUTPUT_FILE} ({os.path.getsize(OUTPUT_FILE):,} bytes)")

if __name__ == "__main__":
    generate_html()
