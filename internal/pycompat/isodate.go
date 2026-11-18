package pycompat

import (
	"fmt"
	"time"
)

// DateFromISOFormat is Python 3.12's datetime.date.fromisoformat(s), ported
// from CPython's C implementation (_datetimemodule.c, parse_isoformat_date).
// It accepts more than YYYY-MM-DD:
//
//	"2026-08-24", "20260824"                 calendar date
//	"2026-W35", "2026W35", "2026-W35-1"...   ISO week date (day defaults to 1)
//	"2026082499"                             trailing bytes after a complete
//	                                         basic-format date are ignored,
//	                                         as CPython does for a 10-byte input
//
// The input must be 7, 8 or 10 bytes of UTF-8 and the digits ASCII. The
// result is midnight UTC on that day. The error carries no detail: callers
// (schedule.load) replace it with their own message, as Python does.
func DateFromISOFormat(s string) (time.Time, error) {
	invalid := fmt.Errorf("%w: Invalid isoformat string: %s", ErrValue, StrRepr(s))
	n := len(s)
	if n != 7 && n != 8 && n != 10 {
		return time.Time{}, invalid
	}
	// CPython reads a NUL-terminated buffer; reading past the end yields 0.
	at := func(i int) byte {
		if i < n {
			return s[i]
		}
		return 0
	}
	digits := func(p, count int) (int, int, bool) {
		v := 0
		for i := 0; i < count; i++ {
			c := at(p + i)
			if c < '0' || c > '9' {
				return 0, p, false
			}
			v = v*10 + int(c-'0')
		}
		return v, p + count, true
	}
	year, p, ok := digits(0, 4)
	if !ok {
		return time.Time{}, invalid
	}
	sep := at(p) == '-'
	if sep {
		p++
	}
	if at(p) == 'W' {
		p++
		week, q, ok := digits(p, 2)
		if !ok {
			return time.Time{}, invalid
		}
		p = q
		day := 1
		if p < n {
			if sep {
				if at(p) != '-' {
					return time.Time{}, invalid
				}
				p++
			}
			if day, _, ok = digits(p, 1); !ok {
				return time.Time{}, invalid
			}
		}
		t, ok := isoWeekToDate(year, week, day)
		if !ok {
			return time.Time{}, invalid
		}
		return t, nil
	}
	month, p, ok := digits(p, 2)
	if !ok {
		return time.Time{}, invalid
	}
	if sep {
		if at(p) != '-' {
			return time.Time{}, invalid
		}
		p++
	}
	day, _, ok := digits(p, 2)
	if !ok {
		return time.Time{}, invalid
	}
	t, ok := validDate(year, month, day)
	if !ok {
		return time.Time{}, invalid
	}
	return t, nil
}

func validDate(y, m, d int) (time.Time, bool) {
	if y < 1 || y > 9999 || m < 1 || m > 12 || d < 1 {
		return time.Time{}, false
	}
	t := time.Date(y, time.Month(m), d, 0, 0, 0, 0, time.UTC)
	if t.Day() != d { // 30 February rolls over into March
		return time.Time{}, false
	}
	return t, true
}

// isoWeekToDate is CPython's iso_to_ymd followed by the date range check.
func isoWeekToDate(year, week, day int) (time.Time, bool) {
	if year < 1 || year > 9999 {
		return time.Time{}, false
	}
	if week <= 0 || week >= 53 {
		ok := false
		if week == 53 {
			// A year has 53 ISO weeks when it starts on a Thursday, or on a
			// Wednesday in a leap year.
			first := time.Date(year, 1, 1, 0, 0, 0, 0, time.UTC).Weekday()
			leap := year%4 == 0 && (year%100 != 0 || year%400 == 0)
			ok = first == time.Thursday || (first == time.Wednesday && leap)
		}
		if !ok {
			return time.Time{}, false
		}
	}
	if day <= 0 || day >= 8 {
		return time.Time{}, false
	}
	// Monday of ISO week 1 is the Monday on or before 4 January.
	jan4 := time.Date(year, 1, 4, 0, 0, 0, 0, time.UTC)
	monday := jan4.AddDate(0, 0, -((int(jan4.Weekday()) + 6) % 7))
	t := monday.AddDate(0, 0, (week-1)*7+day-1)
	if t.Year() < 1 || t.Year() > 9999 {
		return time.Time{}, false
	}
	return t, true
}
