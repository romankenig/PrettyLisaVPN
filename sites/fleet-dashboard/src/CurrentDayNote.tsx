import { formatDay } from "./analytics";

export default function CurrentDayNote({ date }: { date?: string }) {
  return date ? <p className="device-current-day analytics-current-day"><strong>{formatDay(date)} · неполный день</strong> · обновление раз в минуту</p> : null;
}
