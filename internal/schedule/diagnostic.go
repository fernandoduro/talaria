package schedule

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"unicode/utf8"
)

// jsonDiagnostic translates the decoder's common syntax diagnostics into the
// JSONDecodeError wording Python inserts into the fail-closed operator message.
// The safety decision never depends on this translation: any decode error aborts.
func jsonDiagnostic(data []byte, err error) string {
	var syntax *json.SyntaxError
	if !errors.As(err, &syntax) {
		return err.Error()
	}
	pos := max(0, min(len(data), int(syntax.Offset)))
	msg := syntax.Error()
	reason := ""
	switch {
	case strings.Contains(msg, "after object key:value pair"), strings.Contains(msg, "after array element"):
		reason = "Expecting ',' delimiter"
	case strings.Contains(msg, "after object key"):
		reason = "Expecting ':' delimiter"
	case strings.Contains(msg, "object key string"):
		reason = "Expecting property name enclosed in double quotes"
	case strings.Contains(msg, "beginning of value"):
		reason = "Expecting value"
	default:
		// Decoder.Token reports an invalid first object key without a suffix.
		if bytes.HasPrefix(bytes.TrimSpace(data), []byte("{")) {
			reason = "Expecting property name enclosed in double quotes"
		} else {
			return err.Error()
		}
	}
	prefix := string(data[:pos])
	line := strings.Count(prefix, "\n") + 1
	last := strings.LastIndex(prefix, "\n")
	col := utf8.RuneCountInString(prefix[last+1:]) + 1
	cp := utf8.RuneCountInString(prefix)
	return fmt.Sprintf("%s: line %d column %d (char %d)", reason, line, col, cp)
}
