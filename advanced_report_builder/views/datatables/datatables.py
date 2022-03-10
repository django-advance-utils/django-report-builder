from django_datatables.datatables import DatatableView, DatatableError
from django_datatables.helpers import row_link
from django_menus.menu import MenuItem

from advanced_report_builder.columns import ArrowColumn
from advanced_report_builder.exceptions import ReportError
from advanced_report_builder.utils import get_field_details, make_slug_str
from advanced_report_builder.utils import split_slug
from advanced_report_builder.views.datatables.utils import TableUtilsMixin
from advanced_report_builder.views.report import ReportBase


class TableView(ReportBase, TableUtilsMixin, DatatableView):
    template_name = 'advanced_report_builder/datatables/report.html'
    menu_display = ''

    def add_tables(self):
        return None

    def dispatch(self, request, *args, **kwargs):
        self.slug = split_slug(self.kwargs['slug'])
        self.report = kwargs.get('report')
        self.table_report = self.report.tablereport
        self.dashboard_report = kwargs.get('dashboard_report')
        self.enable_edit = kwargs.get('enable_edit')
        if self.dashboard_report:
            table_id = f'tabledashboard_{self.dashboard_report.id}'
        else:
            table_id = f'table_{self.table_report.id}'

        self.base_model = self.table_report.get_base_modal()
        self.add_table(table_id, model=self.base_model)
        try:
            return super().dispatch(request, *args, **kwargs)
        except DatatableError as de:
            raise ReportError(de.args[0])

    def setup_table(self, table):
        table.extra_filters = self.extra_filters
        base_model = self.table_report.get_base_modal()
        table_fields = self.table_report.table_fields
        pivot_fields = self.table_report.pivot_fields
        fields_used = set()
        report_builder_class = getattr(base_model,
                                       self.table_report.report_type.report_builder_class_name, None)
        self.process_query_results(report_builder_class=report_builder_class,
                                   table=table,
                                   base_model=base_model,
                                   fields_used=fields_used,
                                   table_fields=table_fields,
                                   pivot_fields=pivot_fields)

        table.table_options['pageLength'] = self.table_report.page_length
        table.table_options['bStateSave'] = False
        if self.table_report.has_clickable_rows and self.table_report.link_field:
            table.table_classes.append('row_link')
            table.add_columns(ArrowColumn(column_name='arrow_icon'))
            _, col_type_override, _, _ = get_field_details(base_model=base_model,
                                                           field=self.table_report.link_field)
            if isinstance(col_type_override.field, list):
                field = col_type_override.field[0]
            else:
                field = 'id'
            if field not in fields_used:
                table.add_columns(f'.{field}')
            table.table_options['row_href'] = row_link(col_type_override.url, field)

    def get_title(self):
        title = super().get_title()
        report_queries_count = self.table_report.reportquery_set.all().count()
        if report_queries_count > 1:
            version_name = self.get_report_query(report=self.table_report).name
            title += f' ({version_name})'
        return title

    def add_to_context(self, **kwargs):
        return {'title': self.get_title(),
                'table_report': self.table_report}

    def setup_menu(self):
        super().setup_menu()
        if self.dashboard_report and self.enable_edit:
            report_menu = self.pod_dashboard_edit_menu()
        elif self.dashboard_report and not self.enable_edit:
            report_menu = self.pod_dashboard_view_menu()
        else:
            report_menu = self.pod_report_menu()

        self.add_menu('button_menu', 'button_group').add_items(
            *report_menu,
            *self.queries_menu(),
        )

    def pod_dashboard_edit_menu(self):
        return [MenuItem(f'advanced_report_builder:dashboard_report_modal,pk-{self.dashboard_report.id}',
                         menu_display='Edit',
                         font_awesome='fas fa-pencil-alt', css_classes=['btn-primary'])]

    # noinspection PyMethodMayBeStatic
    def pod_dashboard_view_menu(self):
        return []

    def pod_report_menu(self):

        query_id = self.slug.get(f'query{self.table_report.id}')
        slug_str = ''
        if query_id:
            slug_str = f'-query_id-{query_id}'

        return self.edit_report_menu(request=self.request, chart_report_id=self.table_report.id, slug_str=slug_str)

    def edit_report_menu(self, request, chart_report_id, slug_str):
        return [MenuItem(f'advanced_report_builder:table_modal,pk-{chart_report_id}{slug_str}',
                         menu_display='Edit',
                         font_awesome='fas fa-pencil-alt', css_classes=['btn-primary']),
                *self.duplicate_menu(request=self.request, report_id=chart_report_id)
                ]

    # noinspection PyMethodMayBeStatic
    def queries_menu(self):
        report_queries = self.table_report.reportquery_set.all()
        if len(report_queries) > 1:
            dropdown = []
            for report_query in report_queries:
                slug_str = make_slug_str(self.slug, overrides={f'query{self.table_report.id}': report_query.id})
                dropdown.append((self.request.resolver_match.view_name,
                                 report_query.name, {'url_kwargs': {'slug': slug_str}}))
            return [MenuItem(menu_display='Version', no_hover=True, css_classes='btn-secondary',
                             dropdown=dropdown)]
        return []
