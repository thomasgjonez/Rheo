import { useEffect, useId, useState } from "react";
import { searchPlaces } from "../lib/api";
import type { Place } from "../types";

interface Props {
  label: string;
  marker: "A" | "B";
  text: string;
  place: Place | null;
  active: boolean;
  onText: (text: string) => void;
  onPick: (place: Place) => void;
  onClear: () => void;
  onFocus: () => void;
}

export function SearchBox({ label, marker, text, place, active, onText, onPick, onClear, onFocus }: Props) {
  const [options, setOptions] = useState<Place[]>([]);
  const [note, setNote] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(-1);
  const [typing, setTyping] = useState(false);
  const listId = useId();

  useEffect(() => {
    if (!typing || text.trim().length < 3) {
      setOptions([]);
      setNote(null);
      return;
    }
    const ctrl = new AbortController();
    const handle = setTimeout(async () => {
      try {
        const res = await searchPlaces(text, ctrl.signal);
        setOptions(res.results);
        setNote(res.error ?? (res.results.length === 0 ? "No matches in the coverage area" : null));
        setHighlight(-1);
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          setOptions([]);
          setNote("Address search is unavailable");
        }
      }
    }, 250);
    return () => {
      clearTimeout(handle);
      ctrl.abort();
    };
  }, [text, typing]);

  function choose(p: Place) {
    setTyping(false);
    setOpen(false);
    onPick(p);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown" && options.length) {
      e.preventDefault();
      setOpen(true);
      setHighlight((h) => (h + 1) % options.length);
    } else if (e.key === "ArrowUp" && options.length) {
      e.preventDefault();
      setHighlight((h) => (h <= 0 ? options.length - 1 : h - 1));
    } else if (e.key === "Enter") {
      const pick = options[highlight >= 0 ? highlight : 0];
      if (open && pick) {
        e.preventDefault();
        choose(pick);
      }
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  function onBlur() {
    setOpen(false);
    setTyping(false);
    if (place && text !== place.label) onText(place.label);
  }

  const showList = open && typing && (options.length > 0 || note);

  return (
    <div className={`field${active ? " field--active" : ""}`}>
      <span className={`pin pin--${marker}`} aria-hidden="true">
        {marker}
      </span>
      <input
        role="combobox"
        aria-label={label}
        aria-expanded={Boolean(showList)}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={highlight >= 0 ? `${listId}-${highlight}` : undefined}
        autoComplete="off"
        spellCheck={false}
        placeholder={marker === "A" ? "Start: address, place, or click the map" : "Destination"}
        value={text}
        onChange={(e) => {
          setTyping(true);
          setOpen(true);
          onText(e.target.value);
        }}
        onFocus={(e) => {
          onFocus();
          e.currentTarget.select();
        }}
        onBlur={onBlur}
        onKeyDown={onKeyDown}
      />
      {place && (
        <button type="button" className="icon-btn" aria-label={`Clear ${label}`} onClick={onClear}>
          &times;
        </button>
      )}
      {showList && (
        <ul id={listId} role="listbox" className="suggestions">
          {options.map((o, i) => (
            <li
              key={`${o.lat},${o.lon},${o.label}`}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === highlight}
              className={i === highlight ? "is-highlighted" : undefined}
              onMouseDown={(e) => {
                e.preventDefault();
                choose(o);
              }}
              onMouseEnter={() => setHighlight(i)}
            >
              {o.label}
            </li>
          ))}
          {options.length === 0 && note && (
            <li className="suggestions__note" aria-disabled="true">
              {note}
            </li>
          )}
        </ul>
      )}
    </div>
  );
}
