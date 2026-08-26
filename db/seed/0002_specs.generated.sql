-- =====================================================================
-- GENERIERT von tools/gen_spec_seed.py - NICHT VON HAND AENDERN.
-- Quelle: specs/slot_schema.v1.json, specs/photo_spec.v1.json
-- =====================================================================

-- ---------------------------------------------------- Slot-Schema
insert into slot_schema (id, version, definition) values
  ('TC-A@1.0.0', '1.0.0', $json${
  "id": "TC-A",
  "version": "1.0.0",
  "status": "An den echten leeren Vorlagen ausgemessen (2026-08-26, 1438 x 2000 px = 63 x 88 mm). blau, schwarz und gold teilen dieses Raster; gold sitzt 0,6 mm rechts und 1,4 mm tiefer, premium hat ein eigenes Layout - beides in slot_overrides.",
  "note": "Alle vier Templates teilen dieses Schema. Es unterscheiden sich nur Grafik, Farbwelt und Druckspezifikation. Ergebnis: ein Renderer, ein QA-Regelsatz, ein Golden Set.",
  "geometry": {
    "unit": "mm",
    "origin": "oben links des Endformats (Trim). Negative Werte reichen in den Anschnitt.",
    "trim_width": 63.0,
    "trim_height": 88.0,
    "bleed": 2.0,
    "safe_margin": 4.0,
    "min_dpi": 300
  },
  "front": {
    "slots": [
      {
        "id": "photo",
        "type": "image",
        "box": {
          "x": 5.0,
          "y": 12.5,
          "w": 53.0,
          "h": 50.0
        },
        "fit_mode": "ANCHOR",
        "anchors": {
          "eye_line_ratio": 0.38,
          "head_height_ratio": 0.46,
          "center_x_ratio": 0.5,
          "tolerance_ratio": 0.02
        },
        "note": "Die Ankerregel ist der Grund, warum 60 unterschiedlich geschnittene Handyfotos wie ein Set aussehen. Der Renderer berechnet Skalierung und Versatz aus den Landmarks aus Schicht A.",
        "required": true,
        "derived_requirements": {
          "head_height_mm_on_card": 23.0,
          "min_head_height_px": 272,
          "note": "HERGELEITET aus box.h und head_height_ratio, nicht geschaetzt: damit der Kopf nach der Ankerskalierung noch 300 dpi hat, muss er im Quellbild mindestens 283 px hoch sein. tools/photo_requirements.py rechnet das aus dem Schema nach; Gate 1 prueft die Folge (LOW_EFFECTIVE_DPI).",
          "min_image_width_per_head_height": 2.304,
          "min_above_eye_per_head_height": 0.826,
          "min_below_eye_per_head_height": 1.348,
          "framing_note": "Damit das Bild den Slot ohne Aufskalieren deckt, muss um den Kopf herum genug Bild liegen: Breite >= 2.22 x Kopfhoehe, ueber der Augenlinie >= 0.83 x Kopfhoehe, darunter >= 1.35 x Kopfhoehe. Alles aus box und anchors hergeleitet, siehe tools/photo_requirements.py."
        },
        "coverage_scale_tolerance": 0.15
      },
      {
        "id": "club_logo",
        "type": "image",
        "box": {
          "x": 4.0,
          "y": 4.0,
          "w": 12.0,
          "h": 12.0
        },
        "fit_mode": "COVER",
        "source": "team_design_context.club_logo",
        "required": false,
        "hidden": true,
        "note": "In den vier Prizm-Vorlagen nicht vorgesehen - dort stehen nur Name, Verein, Trikotnummer, Unterschrift und Auflage. Bleibt fuer spaetere Designs erhalten und wird ueber slot_overrides wieder eingeblendet."
      },
      {
        "id": "season",
        "type": "text",
        "box": {
          "x": 43.0,
          "y": 4.5,
          "w": 16.0,
          "h": 4.0
        },
        "source": "team.season",
        "font": "display",
        "size_pt": 8.0,
        "min_size_pt": 7.0,
        "align": "right",
        "transform": "none",
        "max_lines": 1,
        "required": false,
        "hidden": true,
        "note": "In den vier Prizm-Vorlagen nicht vorgesehen - dort stehen nur Name, Verein, Trikotnummer, Unterschrift und Auflage. Bleibt fuer spaetere Designs erhalten und wird ueber slot_overrides wieder eingeblendet."
      },
      {
        "id": "player_name",
        "type": "text",
        "box": {
          "x": 11.5,
          "y": 4.0,
          "w": 31.5,
          "h": 4.2
        },
        "source": "person.display_name",
        "font": "display",
        "size_pt": 10.0,
        "min_size_pt": 8.0,
        "align": "center",
        "transform": "uppercase",
        "max_lines": 1,
        "qa_region": true,
        "note": "Das schwarze Namensband der Vorlage reicht von 2,3 bis 8,6 mm und ist 34 mm breit. Der TEXT sitzt nur in dessen unterer Haelfte: ab 4 mm beginnt die Sicherheitszone, und Schrift darf beim Schneiden nicht angeschnitten werden - Grafik darf das, Text nicht. 10 pt ist die groesste Groesse, die in die 4,2 mm Boxhoehe passt; waere sie groesser, wuerde JEDER Name verkleinert und die Karten haetten nie dieselbe Namensgroesse. Prueffeld fuer Gate 3a; Autofit unter min_size_pt ist ein Gate-1-Fehler.",
        "required": true
      },
      {
        "id": "jersey_number",
        "type": "text",
        "box": {
          "x": 45.0,
          "y": 13.5,
          "w": 12.0,
          "h": 8.0
        },
        "source": "person.jersey_number",
        "font": "display",
        "size_pt": 19.0,
        "min_size_pt": 15.0,
        "align": "right",
        "transform": "none",
        "max_lines": 1,
        "qa_region": true,
        "required": false
      },
      {
        "id": "position",
        "type": "text",
        "box": {
          "x": 4.0,
          "y": 77.6,
          "w": 30.0,
          "h": 3.2
        },
        "source": "person.role_label",
        "font": "body",
        "size_pt": 7.5,
        "min_size_pt": 6.5,
        "align": "left",
        "transform": "uppercase",
        "letter_spacing_em": 0.08,
        "max_lines": 1,
        "required": false,
        "hidden": true,
        "note": "In den vier Prizm-Vorlagen nicht vorgesehen - dort stehen nur Name, Verein, Trikotnummer, Unterschrift und Auflage. Bleibt fuer spaetere Designs erhalten und wird ueber slot_overrides wieder eingeblendet."
      },
      {
        "id": "club_name",
        "type": "text",
        "box": {
          "x": 11.5,
          "y": 8.8,
          "w": 31.5,
          "h": 3.2
        },
        "source": "club.name",
        "font": "body",
        "size_pt": 7.0,
        "min_size_pt": 5.5,
        "align": "center",
        "transform": "none",
        "max_lines": 1,
        "qa_region": true,
        "required": true
      },
      {
        "id": "signature",
        "type": "image",
        "box": {
          "x": 12.3,
          "y": 66.8,
          "w": 38.4,
          "h": 11.4
        },
        "source": "person.signature",
        "fit_mode": "CONTAIN",
        "required": false,
        "note": "Weisses Feld der Vorlage unter 'AUTHENTIC SIGNATURE'. Drei Wege fuer die Familie: unterschreiben, Bild hochladen, tippen. Fehlt sie, bleibt das Feld leer - das ist kein Fehler."
      },
      {
        "id": "serial",
        "type": "text",
        "box": {
          "x": 25.5,
          "y": 79.8,
          "w": 12.0,
          "h": 4.0
        },
        "source": "card.copy_index_of_total",
        "font": "display",
        "size_pt": 7.0,
        "min_size_pt": 6.0,
        "align": "center",
        "transform": "none",
        "max_lines": 1,
        "qa_region": true,
        "required": true,
        "note": "Auflagennummer, in der Vorlage als '01/01' vorgezeichnet. Gate 3a liest sie zurueck."
      }
    ],
    "overlays": [
      {
        "id": "signature_plate",
        "box": {
          "x": 10.5,
          "y": 60.6,
          "w": 42.0,
          "h": 19.4
        }
      },
      {
        "id": "ornament_left",
        "box": {
          "x": 0.0,
          "y": 31.0,
          "w": 7.0,
          "h": 23.0
        }
      },
      {
        "id": "ornament_right",
        "box": {
          "x": 56.0,
          "y": 31.0,
          "w": 7.0,
          "h": 23.0
        }
      }
    ],
    "overlays_note": "Ausschnitte DERSELBEN flachen Vorlagendatei, die nach dem freigestellten Spieler noch einmal gezeichnet werden. Damit sitzt die Unterschriftenplatte vor dem Spieler, ohne dass die Grafik in Ebenen zerlegt werden muesste. Ein Bild je Design genuegt.",
    "patches": [
      {
        "id": "serial_overprint",
        "box": {
          "x": 25.5,
          "y": 79.6,
          "w": 12.0,
          "h": 6.0
        },
        "source_offset": {
          "dx": -13.0,
          "dy": 0.0
        },
        "note": "Quelle liegt 13 mm LINKS daneben, nicht darueber: 8 mm hoeher beginnt die Unterschriftenplatte, von dort holt man weisse Flaeche statt Kristall. Auf gleicher Hoehe daneben stimmt die Struktur."
      }
    ],
    "patches_note": "BEFUND 2026-08-26: auf allen vier gelieferten Vorlagen ist die Auflagennummer bereits eingedruckt (01/01, bei Premium #01/01). Sie wechselt aber je Kopie. Bis es Fassungen ohne sie gibt, wird die Stelle mit Struktur von 8 mm darueber ueberdeckt - auf Kristall unsichtbar, weil das Muster zufaellig ist. Sauberer ist ein Export ohne die Nummer."
  },
  "back": {
    "slots": [
      {
        "id": "player_name_back",
        "type": "text",
        "box": {
          "x": 4.0,
          "y": 8.0,
          "w": 55.0,
          "h": 7.0
        },
        "source": "person.display_name",
        "font": "display",
        "size_pt": 12.0,
        "min_size_pt": 8.0,
        "align": "center",
        "transform": "uppercase",
        "max_lines": 2,
        "qa_region": true,
        "required": true
      },
      {
        "id": "club_season_back",
        "type": "text",
        "box": {
          "x": 4.0,
          "y": 16.0,
          "w": 55.0,
          "h": 4.5
        },
        "source": "club.name + ' · ' + team.season",
        "font": "body",
        "size_pt": 8.0,
        "min_size_pt": 6.5,
        "align": "center",
        "max_lines": 1,
        "required": true
      },
      {
        "id": "stats_block",
        "type": "keyvalue",
        "box": {
          "x": 8.0,
          "y": 24.0,
          "w": 47.0,
          "h": 16.0
        },
        "source": "person.stats",
        "font": "body",
        "size_pt": 7.0,
        "min_size_pt": 6.0,
        "max_rows": 4,
        "required": false
      },
      {
        "id": "qr",
        "type": "qr",
        "box": {
          "x": 21.5,
          "y": 42.0,
          "w": 20.0,
          "h": 20.0
        },
        "payload_source": "card_twin.public_token",
        "url_pattern": "https://{resolver_host}/k/{token}",
        "error_correction": "Q",
        "min_module_mm": 0.4,
        "quiet_zone_modules": 4,
        "max_payload_bytes": 74,
        "forbid_finishing_overlay": true,
        "min_contrast_ratio": 7.0,
        "note": "PAYLOAD-BUDGET: 74 Byte. Hergeleitet aus der Boxgroesse, nicht geschaetzt - bei 20 mm Box, 4 Modulen Ruhezone und 0.40 mm Mindestmodul ist Version 6 (41 Module) die groesste noch sauber druckbare Version, und die traegt im Byte-Modus bei ECC Q 74 Byte. Der Token belegt 22, 'https://' und '/k/' weitere 11 - fuer den Host bleiben rund 40 Zeichen. Praktisch passt damit jeder realistische Domainname. Ein KURZER Host ist trotzdem besser: er senkt die QR-Version und vergroessert damit die Module (k.mrc.cards -> 0.49 mm, karte.myrookiecard.de -> 0.44 mm), was das Scannen einer zerkratzten Karte robuster macht. engine/layout.py:qr_plan rechnet das je Karte aus, Gate 1 prueft es.",
        "required": true
      },
      {
        "id": "qr_caption",
        "type": "text",
        "box": {
          "x": 4.0,
          "y": 64.0,
          "w": 55.0,
          "h": 4.0
        },
        "static_text_de": "Scanne den Code für deine digitale Karte",
        "font": "body",
        "size_pt": 7.0,
        "min_size_pt": 6.0,
        "align": "center",
        "max_lines": 1,
        "required": true
      },
      {
        "id": "legal_line",
        "type": "text",
        "box": {
          "x": 4.0,
          "y": 77.8,
          "w": 55.0,
          "h": 5.6
        },
        "source": "config.legal_line",
        "font": "body",
        "size_pt": 5.0,
        "min_size_pt": 5.0,
        "align": "center",
        "max_lines": 2,
        "required": true
      }
    ]
  },
  "families": [
    {
      "id": "DESIGN-1",
      "name": "Blau Prizm",
      "role": null,
      "print_spec": "PS-STD",
      "token_per_copy": true,
      "slot_overrides": {},
      "note": "Blau Prizm. Traegt das Basisraster unveraendert."
    },
    {
      "id": "DESIGN-2",
      "name": "Schwarz Prizm",
      "role": null,
      "print_spec": "PS-STD",
      "token_per_copy": true,
      "slot_overrides": {},
      "note": "Schwarz Prizm. Deckungsgleich mit Blau (Messabweichung < 0,4 mm)."
    },
    {
      "id": "DESIGN-3",
      "name": "Gold Prizm",
      "role": null,
      "print_spec": "PS-GOLD",
      "token_per_copy": true,
      "slot_overrides": {
        "signature": {
          "box": {
            "x": 12.9,
            "y": 68.2,
            "w": 38.4,
            "h": 11.4
          }
        }
      },
      "note": "Gold Prizm. Die Unterschriftenplatte sitzt 0,6 mm rechts und 1,4 mm tiefer als bei Blau und Schwarz - automatisch gemessen, nicht geschaetzt."
    },
    {
      "id": "DESIGN-4",
      "name": "Premium Gold",
      "role": null,
      "print_spec": "PS-GOLD",
      "token_per_copy": true,
      "slot_overrides": {
        "photo": {
          "box": {
            "x": 7.0,
            "y": 14.0,
            "w": 49.0,
            "h": 58.0
          }
        },
        "player_name": {
          "box": {
            "x": 11.5,
            "y": 75.0,
            "w": 40.0,
            "h": 4.6
          },
          "align": "center"
        },
        "club_name": {
          "box": {
            "x": 11.5,
            "y": 80.0,
            "w": 40.0,
            "h": 3.2
          },
          "align": "center"
        },
        "jersey_number": {
          "box": {
            "x": 25.5,
            "y": 64.0,
            "w": 12.0,
            "h": 8.0
          },
          "align": "center"
        },
        "signature": {
          "box": {
            "x": 16.0,
            "y": 56.0,
            "w": 31.0,
            "h": 9.0
          }
        },
        "serial": {
          "box": {
            "x": 44.2,
            "y": 10.0,
            "w": 13.4,
            "h": 4.6
          },
          "align": "right"
        }
      },
      "note": "Premium Gold. Eigenes Layout: Name und Verein unten auf der dunklen Platte, Auflagennummer oben rechts, kein vorgesehenes Unterschriftenfeld - der Slot liegt behelfsweise ueber dem unteren Bilddrittel. Hier braucht es eine Designentscheidung. GESPERRT bis zu einem Export ohne eingedruckte Auflagennummer, siehe blocker.",
      "overlays": [
        {
          "id": "kopfband",
          "box": {
            "x": 0.0,
            "y": 0.0,
            "w": 63.0,
            "h": 13.5
          }
        },
        {
          "id": "ecke_links",
          "box": {
            "x": 0.0,
            "y": 33.0,
            "w": 8.0,
            "h": 22.0
          }
        },
        {
          "id": "ecke_rechts",
          "box": {
            "x": 55.0,
            "y": 33.0,
            "w": 8.0,
            "h": 22.0
          }
        },
        {
          "id": "namensplatte",
          "box": {
            "x": 0.0,
            "y": 72.5,
            "w": 63.0,
            "h": 15.5
          }
        }
      ],
      "blocker": {
        "code": "TEMPLATE_HAS_PRINTED_SERIAL",
        "severity": "HARD",
        "note": "Die eingedruckte Nummer '#01/01' sitzt direkt an der Kante des Kopfbands. Anders als bei den Kristallvorlagen gibt es auf dieser Vorlage keine Stelle, deren Struktur als Ersatz taugt - automatisch geprueft: die beste Fundstelle weicht in Farbe und Streuung deutlich ab. Ueberdecken waere sichtbares Flicken. Es braucht einen Export ohne die Nummer, bevor Premium in Produktion geht."
      }
    },
    {
      "id": "DESIGN-5",
      "name": "Mannschaftskarte (Konzept)",
      "role": null,
      "print_spec": "PS-STD",
      "token_per_copy": true,
      "slot_overrides": {
        "photo": {
          "fit_mode": "COVER"
        },
        "player_name": {
          "source": "team.name"
        },
        "jersey_number": {
          "required": false,
          "hidden": true
        },
        "signature": {
          "hidden": true
        }
      },
      "note": "Noch nicht bestellt, aber der Beleg dafuer, dass slot_overrides traegt: ein Gruppenfoto hat keine Kopf-Anker, also greift fit_mode COVER auf demselben Slot, der Name kommt vom Team statt von der Person, Rueckennummer und Unterschrift entfallen. Kommt spaeter ein Design mit anderen Angaben, geht es genauso."
    }
  ],
  "token_policy": {
    "decision": "ein QR-Token je physischer Kopie",
    "rationale": "macht jede gedruckte Karte einzeln identifizierbar - Voraussetzung fuer eine spaetere Tausch- oder Echtheitsfunktion",
    "cost": "drei Kopien = drei Rueckseiten. Die Vorderseite und die teuren QA-Gates 3a-3c werden ueber front_fingerprint wiederverwendet.",
    "irreversible": true
  }
}$json$::jsonb)
on conflict (id) do update set definition = excluded.definition;

-- ---------------------------------------------------- photo_spec
update photo_spec set is_active = false where is_active;
insert into photo_spec (version, rules, is_active) values
  ('1.0.0', $json${
  "version": "1.0.0",
  "status": "Schwellwerte am 2026-08-26 an fuenf echten Elternfotos kalibriert (assets/beispielfotos, tools/photo_check.py). Nach den ersten Betriebswochen aus echten Ablehnungsgruenden nachschaerfen.",
  "applies_to_slot_schema": "TC-A@1.0.0",
  "note": "Eine Quelle, drei Ausspielungen: die Erklaerstrecke beim Partner, die Sofortpruefung im Upload-Dialog (Gate -1) und die verbindliche Eingangsvalidierung (Gate 0) werden alle hieraus abgeleitet. Ohne gemeinsame Quelle laufen sie garantiert auseinander.",
  "normalization": {
    "note": "Laeuft VOR jeder Pruefung. Zwei Fallen, die jedes Foto-Backend einmal treffen.",
    "steps": [
      {
        "id": "heic_decode",
        "reason": "iPhone-Standardformat, viele Bibliotheken lesen es nicht"
      },
      {
        "id": "exif_rotate",
        "reason": "nicht angewandte EXIF-Rotation laesst das Bild quer liegen; jede Landmark-Pruefung schlaegt fehl und meldet faelschlich 'kein Gesicht erkannt'"
      },
      {
        "id": "strip_exif_pii",
        "reason": "GPS und Geraetedaten entfernen, bevor das Asset gespeichert wird"
      },
      {
        "id": "to_srgb",
        "reason": "einheitlicher Arbeitsfarbraum vor der Freistellung"
      }
    ]
  },
  "accepted_formats": [
    "image/jpeg",
    "image/png",
    "image/heic",
    "image/heif"
  ],
  "max_upload_bytes": 26214400,
  "rules": [
    {
      "id": "resolution",
      "metric": "min(width_px, height_px * 0.75)",
      "pass": ">= 900 x 1200 px",
      "class_b_from": "700 x 900 px",
      "fail_below": "700 x 900 px",
      "reason_code": "PHOTO_TOO_SMALL",
      "message_de": "Das Bild ist zu klein für den Druck.",
      "hint_de": "Schick uns das Originalfoto statt einer verkleinerten Kopie aus einem Chat.",
      "checked_by": [
        "PRECHECK",
        "GATE0"
      ],
      "note": "Die Bildgroesse allein entscheidet nichts - massgeblich ist die KOPFHOEHE in Pixeln (Regel head_height_px). 900 x 1200 px sind der bequeme Richtwert, bei dem ein regelkonformer Ausschnitt die Kopfhoehe sicher erreicht."
    },
    {
      "id": "head_height_px",
      "metric": "Kopfhöhe im Quellbild in Pixeln",
      "pass": ">= 272 px",
      "class_b_from": "231 px",
      "fail_below": "231 px",
      "reason_code": "PHOTO_HEAD_TOO_FEW_PIXELS",
      "message_de": "Der Kopf ist im Bild zu klein, um scharf gedruckt zu werden.",
      "hint_de": "Geh näher ran, statt das Bild später zu vergrößern.",
      "derived_from": "slot_schema TC-A: photo.box.h × anchors.head_height_ratio bei 300 dpi",
      "note": "Die eigentliche Aufloesungsregel. Ein 4000-px-Foto mit winzigem Kopf ist unbrauchbar, ein knappes Foto mit formatfuellendem Kopf ist bestens. Gate 1 prueft die Folge nach der Ankerskalierung erneut.",
      "checked_by": [
        "PRECHECK",
        "GATE0"
      ]
    },
    {
      "id": "framing_margin_around_head",
      "metric": "Bildbreite und Abstand ober-/unterhalb der Augenlinie, jeweils im Verhaeltnis zur Kopfhoehe",
      "pass": "Breite >= 2.02 × Kopfhöhe · über den Augen >= 0.83 × · darunter >= 1.35 ×",
      "reason_code": "PHOTO_TOO_TIGHT",
      "message_de": "Es ist zu eng um den Kopf herum fotografiert.",
      "hint_de": "Ein Schritt zurück — Schultern und etwas Luft über dem Kopf gehören mit ins Bild.",
      "derived_from": "slot_schema TC-A: photo.box und photo.anchors",
      "note": "Ohne diese Reserve muss der Renderer aufskalieren, damit kein Rand entsteht - dann wird der Kopf groesser als bei den Mitspielern und die Karte faellt aus dem Set. Bis 15 Prozent Abweichung ist das eine Warnung, darueber ein Fehler.",
      "checked_by": [
        "PRECHECK",
        "GATE0",
        "GATE1"
      ]
    },
    {
      "id": "effective_dpi_after_anchor",
      "metric": "Pixel je mm im Bild-Slot NACH der Ankerskalierung",
      "pass": ">= 300 dpi",
      "fail_below": "250 dpi",
      "reason_code": "PHOTO_LOW_EFFECTIVE_DPI",
      "message_de": "Nach dem Zuschnitt auf die Kartengröße reicht die Auflösung nicht.",
      "hint_de": "Geh näher ran, statt später hineinzuzoomen.",
      "note": "Der haeufigste STILLE Fehler bei Laienfotos: ein knappes Foto rutscht durch das Heranskalieren des Kopfes unter die Grenze. Wird in Gate 1 erneut am Manifest geprueft.",
      "checked_by": [
        "GATE0",
        "GATE1"
      ]
    },
    {
      "id": "single_face",
      "metric": "Anzahl erkannter Gesichter",
      "pass": "genau 1",
      "reason_code": "PHOTO_FACE_COUNT",
      "message_de": "Auf dem Bild ist nicht genau eine Person zu sehen.",
      "hint_de": "Bitte ein Foto, auf dem nur der Spieler zu sehen ist.",
      "checked_by": [
        "PRECHECK",
        "GATE0"
      ]
    },
    {
      "id": "head_height",
      "metric": "Kopfhöhe / Bildhöhe",
      "pass": "0.35 - 0.55",
      "class_b_from": "0.28",
      "reason_code": "PHOTO_HEAD_SIZE",
      "message_de": "Der Kopf ist zu klein beziehungsweise zu groß im Bild.",
      "hint_de": "Oberkörperfoto: von der Kopfoberkante bis etwa zur Brustmitte.",
      "checked_by": [
        "PRECHECK",
        "GATE0"
      ]
    },
    {
      "id": "eye_line_position",
      "metric": "Augenlinie / Bildhöhe",
      "pass": "0.20 - 0.45",
      "reason_code": "PHOTO_FRAMING",
      "message_de": "Der Kopf sitzt zu weit oben oder zu weit unten.",
      "hint_de": "Augen etwa im oberen Drittel, Kopf mittig.",
      "checked_by": [
        "PRECHECK",
        "GATE0"
      ]
    },
    {
      "id": "horizontal_centering",
      "metric": "|Kopfmitte - Bildmitte| / Bildbreite",
      "pass": "<= 0.10",
      "class_b_from": "0.18",
      "reason_code": "PHOTO_OFF_CENTER",
      "message_de": "Der Spieler steht nicht mittig im Bild.",
      "hint_de": "Stell dich in die Mitte des Bildausschnitts.",
      "checked_by": [
        "PRECHECK",
        "GATE0"
      ]
    },
    {
      "id": "shoulders_visible",
      "metric": "Schulterlinie im Bild erkannt",
      "pass": "true",
      "reason_code": "PHOTO_NO_SHOULDERS",
      "message_de": "Die Schultern sind nicht im Bild.",
      "hint_de": "Etwas weiter weg vom Handy - der Oberkörper gehört mit aufs Bild.",
      "checked_by": [
        "PRECHECK",
        "GATE0"
      ]
    },
    {
      "id": "sharpness",
      "metric": "Laplace-Varianz, auf die Gesichtsregion normiert",
      "pass": ">= 120",
      "class_b_from": "70",
      "reason_code": "PHOTO_BLURRY",
      "message_de": "Das Bild ist unscharf.",
      "hint_de": "Halt das Handy still und tipp vorher aufs Gesicht, um scharf zu stellen.",
      "checked_by": [
        "PRECHECK",
        "GATE0"
      ]
    },
    {
      "id": "exposure",
      "metric": "Anteil ausgefressener Lichter/Tiefen in der Gesichtsregion",
      "pass": "<= 2 %",
      "class_b_from": "8 %",
      "reason_code": "PHOTO_EXPOSURE",
      "message_de": "Das Gesicht ist zu hell oder zu dunkel.",
      "hint_de": "Nicht gegen die Sonne oder ein Fenster fotografieren - das Licht sollte von vorne kommen.",
      "checked_by": [
        "PRECHECK",
        "GATE0"
      ]
    },
    {
      "id": "background_calmness",
      "metric": "Kantendichte im Randbereich ausserhalb der Personenmaske",
      "pass": "<= 0.08",
      "class_b_from": "0.16",
      "reason_code": "PHOTO_BUSY_BACKGROUND",
      "message_de": "Der Hintergrund ist zu unruhig.",
      "hint_de": "Stell dich vor eine glatte Wand oder eine ruhige Fläche.",
      "note": "Der wichtigste Einzelwert fuer die Freistellungsquote.",
      "checked_by": [
        "PRECHECK",
        "GATE0"
      ]
    },
    {
      "id": "subject_background_contrast",
      "metric": "Farbabstand Trikot/Haar zu Hintergrund",
      "pass": ">= Schwelle",
      "reason_code": "PHOTO_LOW_CONTRAST_BG",
      "message_de": "Der Hintergrund hat fast dieselbe Farbe wie dein Trikot.",
      "hint_de": "Such dir eine Wand in einer anderen Farbe als dein Trikot.",
      "checked_by": [
        "GATE0"
      ]
    },
    {
      "id": "occlusion",
      "metric": "Vision-Modell: Mütze, Kapuze, verspiegelte Brille, Hand im Gesicht",
      "pass": "keine",
      "reason_code": "PHOTO_OCCLUSION",
      "message_de": "Etwas verdeckt das Gesicht.",
      "hint_de": "Mütze und Kapuze bitte ab, Sonnenbrille auch.",
      "checked_by": [
        "GATE0"
      ]
    },
    {
      "id": "pose",
      "metric": "Kopfrotation (Yaw/Pitch)",
      "pass": "|yaw| <= 20°, |pitch| <= 15°",
      "class_b_from": "|yaw| <= 30°",
      "reason_code": "PHOTO_POSE",
      "message_de": "Der Kopf ist zu stark gedreht oder geneigt.",
      "hint_de": "Schau frontal in die Kamera - so wie auf einem Sammelbild.",
      "checked_by": [
        "PRECHECK",
        "GATE0"
      ]
    },
    {
      "id": "safe_area",
      "metric": "Kopf vollstaendig innerhalb der Sicherheitszone des Bild-Slots",
      "pass": "true",
      "reason_code": "PHOTO_HEAD_CLIPPED",
      "message_de": "Der Kopf würde beim Beschnitt angeschnitten.",
      "hint_de": "Etwas mehr Platz über dem Kopf lassen.",
      "checked_by": [
        "GATE0",
        "GATE1"
      ]
    }
  ],
  "classes": {
    "A": {
      "rule": "alle Regeln im pass-Bereich",
      "handling": "geht ohne Zwischenschritt in die Freistellung"
    },
    "B": {
      "rule": "keine Regel unterhalb ihrer fail-Schwelle, mindestens eine im class_b-Bereich",
      "handling": "automatische Aufbereitung: Aufhellung, Rauschminderung, moderates Upscaling, Farbangleichung an die Template-Farbwelt",
      "note": "Erzeugt IMMER eine neue asset_version mit eigener processing_version. Das Original bleibt unangetastet, der Fingerprint aendert sich, die Kette bleibt lueckenlos."
    },
    "C": {
      "rule": "mindestens eine Regel unterhalb ihrer fail-Schwelle, oder ein HARD-Kriterium verletzt",
      "handling": "Blocker PHOTO_REJECTED mit reason_codes; Nachforderung ueber das Kommunikationsmodul"
    }
  },
  "explainer": {
    "form": "tonlose Schleifenanimation, 8-12 Sekunden, neben dem Upload-Feld",
    "rationale": "Ein Video wird weggeklickt. Eine Animation, die neben dem Upload-Feld laeuft, wird gesehen.",
    "must_work_on": "Mobiltelefon - dort wird der Upload stattfinden",
    "content": "Gegenueberstellung richtig/falsch mit den vier haeufigsten Fehlern",
    "initial_four": [
      "background_calmness",
      "head_height",
      "exposure",
      "sharpness"
    ],
    "review": "Nach vier Betriebswochen aus den tatsaechlichen reason_codes neu bestimmen."
  },
  "messbare_signale": {
    "note": "Was sich OHNE Modell rechnen laesst und deshalb schon im Upload-Dialog laufen kann (Gate -1). tools/photo_check.py ist die Referenzimplementierung; die Zahlen stammen aus den fuenf Beispielfotos, nicht aus der Literatur.",
    "hintergrund_streuung": {
      "messung": "Standardabweichung der Helligkeit im oberen Rand und in den oberen 55 % der Seitenraender",
      "ruhig": "< 30",
      "grenzwertig": "30 bis 45",
      "unruhig": "> 45",
      "gemessen": {
        "glatte Wand": "9 bis 13",
        "Wand mit Tuerrahmen": 34.5,
        "Sportplatz mit Zuschauern": 25.2,
        "Hecke und Zaun": 24.8
      },
      "kalibrierhinweis": "Der erste Ansatz mass den GANZEN Bildrand und meldete jede glatte Wand als unruhig - bei einem Brustbild fuellt der Koerper die untere Kante. Genau der Fehler, den man ohne echte Fotos nicht findet."
    },
    "schaerfe": {
      "messung": "Varianz des Laplace-Filters auf 900 px Breite",
      "scharf": "> 150",
      "grenzwertig": "60 bis 150",
      "unscharf": "< 60",
      "gemessen": {
        "12-MP-Original": 595,
        "3-MP-Kopie": 226,
        "0,8-MP-Kopie": 78.5,
        "hochskalierter Ausschnitt": 22.2
      }
    },
    "belichtung": {
      "zu_dunkel": "mittlere Helligkeit < 60",
      "ueberstrahlt": "> 8 % der Pixel ueber 250"
    }
  },
  "befund_stichprobe": {
    "datum": "2026-08-26",
    "anzahl": 5,
    "ergebnis": {
      "A - direkt verwendbar": 1,
      "B - verwendbar, wenig Reserve": 3,
      "C - Neuaufnahme": 1
    },
    "wichtigster_befund": "Nur EINES der fuenf Fotos war das Original aus der Kamera (12 MP). Es ist zugleich das einzige mit klarer Klasse A. Die uebrigen waren Kopien mit 0,8 bis 5 MP - weitergeleitet, zugeschnitten oder als Bildschirmfoto gesichert. Der Uploaddialog muss deshalb aktiv nach dem Original fragen, nicht nur eine Datei entgegennehmen.",
    "haeufigster_fehler": "Zu nah heran. Das schlechteste Foto hatte eine Kopfhoehe von rund 55 % der Bildhoehe; erlaubt sind bei dieser Bildbreite hoechstens 30 %. Ein zu enger Ausschnitt laesst sich nicht reparieren - fehlendes Bild neben dem Kopf kann niemand nachliefern."
  }
}$json$::jsonb, true)
on conflict (version) do update set rules = excluded.rules, is_active = excluded.is_active;

-- ---------------------------------------------------- Design-Versionen
-- Alle vier Templates auf demselben Slot-Schema: ein Renderer,
-- ein QA-Regelsatz, ein Golden Set.
insert into design_version (family_id, version, slot_schema_id, print_spec_id, assets)
  values ('DESIGN-1', '1.0.0', 'TC-A@1.0.0', 'PS-STD', $json${
  "slot_overrides": {},
  "note": "Blau Prizm. Traegt das Basisraster unveraendert."
}$json$::jsonb)
on conflict (family_id, version) do update set assets = excluded.assets, print_spec_id = excluded.print_spec_id;

insert into design_version (family_id, version, slot_schema_id, print_spec_id, assets)
  values ('DESIGN-2', '1.0.0', 'TC-A@1.0.0', 'PS-STD', $json${
  "slot_overrides": {},
  "note": "Schwarz Prizm. Deckungsgleich mit Blau (Messabweichung < 0,4 mm)."
}$json$::jsonb)
on conflict (family_id, version) do update set assets = excluded.assets, print_spec_id = excluded.print_spec_id;

insert into design_version (family_id, version, slot_schema_id, print_spec_id, assets)
  values ('DESIGN-3', '1.0.0', 'TC-A@1.0.0', 'PS-GOLD', $json${
  "slot_overrides": {
    "signature": {
      "box": {
        "x": 12.9,
        "y": 68.2,
        "w": 38.4,
        "h": 11.4
      }
    }
  },
  "note": "Gold Prizm. Die Unterschriftenplatte sitzt 0,6 mm rechts und 1,4 mm tiefer als bei Blau und Schwarz - automatisch gemessen, nicht geschaetzt."
}$json$::jsonb)
on conflict (family_id, version) do update set assets = excluded.assets, print_spec_id = excluded.print_spec_id;

insert into design_version (family_id, version, slot_schema_id, print_spec_id, assets)
  values ('DESIGN-4', '1.0.0', 'TC-A@1.0.0', 'PS-GOLD', $json${
  "slot_overrides": {
    "photo": {
      "box": {
        "x": 7.0,
        "y": 14.0,
        "w": 49.0,
        "h": 58.0
      }
    },
    "player_name": {
      "box": {
        "x": 11.5,
        "y": 75.0,
        "w": 40.0,
        "h": 4.6
      },
      "align": "center"
    },
    "club_name": {
      "box": {
        "x": 11.5,
        "y": 80.0,
        "w": 40.0,
        "h": 3.2
      },
      "align": "center"
    },
    "jersey_number": {
      "box": {
        "x": 25.5,
        "y": 64.0,
        "w": 12.0,
        "h": 8.0
      },
      "align": "center"
    },
    "signature": {
      "box": {
        "x": 16.0,
        "y": 56.0,
        "w": 31.0,
        "h": 9.0
      }
    },
    "serial": {
      "box": {
        "x": 44.2,
        "y": 10.0,
        "w": 13.4,
        "h": 4.6
      },
      "align": "right"
    }
  },
  "note": "Premium Gold. Eigenes Layout: Name und Verein unten auf der dunklen Platte, Auflagennummer oben rechts, kein vorgesehenes Unterschriftenfeld - der Slot liegt behelfsweise ueber dem unteren Bilddrittel. Hier braucht es eine Designentscheidung. GESPERRT bis zu einem Export ohne eingedruckte Auflagennummer, siehe blocker."
}$json$::jsonb)
on conflict (family_id, version) do update set assets = excluded.assets, print_spec_id = excluded.print_spec_id;

insert into design_version (family_id, version, slot_schema_id, print_spec_id, assets)
  values ('DESIGN-5', '1.0.0', 'TC-A@1.0.0', 'PS-STD', $json${
  "slot_overrides": {
    "photo": {
      "fit_mode": "COVER"
    },
    "player_name": {
      "source": "team.name"
    },
    "jersey_number": {
      "required": false,
      "hidden": true
    },
    "signature": {
      "hidden": true
    }
  },
  "note": "Noch nicht bestellt, aber der Beleg dafuer, dass slot_overrides traegt: ein Gruppenfoto hat keine Kopf-Anker, also greift fit_mode COVER auf demselben Slot, der Name kommt vom Team statt von der Person, Rueckennummer und Unterschrift entfallen. Kommt spaeter ein Design mit anderen Angaben, geht es genauso."
}$json$::jsonb)
on conflict (family_id, version) do update set assets = excluded.assets, print_spec_id = excluded.print_spec_id;

