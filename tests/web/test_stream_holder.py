import pytest

from skat.web.stream_holder import MalformedHolderError, StreamHolder


class TestAStreamHolder:
    def test_reads_back_what_it_wrote(self):
        holder = StreamHolder("table", 'an "odd" account, with: [marks]', "stream")

        assert StreamHolder.parse(holder.encoded()) == holder

    @pytest.mark.parametrize(
        "written",
        ["", "not json", '"table"', '["table", "account"]', '["table", "account", 3]', '["a", "b", "c", "d"]', "{}"],
    )
    def test_refuses_a_name_no_stream_wrote(self, written):
        with pytest.raises(MalformedHolderError):
            StreamHolder.parse(written)
