$(document).ready(function () {
    console.log('yes');
    function add_sortable(selector) {
        $(selector).sortable({
        revert: true,
        opacity: 0.5,
        stop: function (evt, ui) {
            let ids = [];
            $(selector + " .dashboard_item").each(function() {
                ids.push($(this).data("id"));
            });
            ajax_helpers.post_json({"data": {"button": "change_placement", 'ids': ids}});
        }
    });
         $(selector).disableSelection();
    }

    add_sortable(".dashboard_top");
    add_sortable(".dashboard_bottom");
});