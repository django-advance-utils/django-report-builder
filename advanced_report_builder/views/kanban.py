import json
from calendar import monthrange
from datetime import timedelta, date

from django.conf import settings
from django.db.models import Q
from django.forms import CharField, ChoiceField
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.template import Template, Context, TemplateSyntaxError
from django.urls import reverse
from django.views.generic import TemplateView
from django_datatables.columns import ColumnBase, MenuColumn
from django_datatables.helpers import DUMMY_ID, row_link
from django_datatables.widgets import DataTableReorderWidget
from django_menus.menu import MenuItem, HtmlMenu
from django_modals.fields import FieldEx
from django_modals.helper import modal_button, modal_button_method
from django_modals.modals import ModelFormModal, Modal
from django_modals.processes import PROCESS_EDIT_DELETE, PERMISSION_OFF
from django_modals.widgets.select2 import Select2Multiple, Select2

from advanced_report_builder.columns import ReportBuilderNumberColumn
from advanced_report_builder.data_merge.utils import get_menu_fields, get_data_merge_columns
from advanced_report_builder.data_merge.widget import DataMergeWidget
from advanced_report_builder.filter_query import FilterQueryMixin
from advanced_report_builder.globals import DATE_FORMAT_TYPES_DJANGO_FORMAT, DATE_FORMAT_TYPE_DD_MM_YY_SLASH
from advanced_report_builder.models import KanbanReport, KanbanReportLane, ReportType
from advanced_report_builder.toggle import RBToggle
from advanced_report_builder.utils import crispy_modal_link_args, get_field_details
from advanced_report_builder.variable_date import VariableDate
from advanced_report_builder.views.charts_base import ChartJSTable
from advanced_report_builder.views.modals_base import QueryBuilderModalBase
from advanced_report_builder.views.report import ReportBase


class DescriptionColumn(ColumnBase):
    def row_result(self, data, _page_data):
        html = self.options['html']
        for mapped_field, field in self.options['column_map'].items():
            if field in data:
                data[mapped_field] = data[field]
        try:
            template = Template(html)
            context = Context(data)
            return template.render(context)
        except TemplateSyntaxError as e:
            return f'Error in description ({e})'


class KanbanView(ReportBase, FilterQueryMixin, TemplateView):
    number_field = ReportBuilderNumberColumn
    template_name = 'advanced_report_builder/kanban/report.html'
    chart_js_table = ChartJSTable

    def __init__(self, *args, **kwargs):
        self.chart_report = None
        super().__init__(*args, **kwargs)

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

    def dispatch(self, request, *args, **kwargs):
        self.report = kwargs.get('report')
        self.chart_report = self.report.kanbanreport
        return super().dispatch(request, *args, **kwargs)

    def view_filter_extra(self, query, table):
        if table.extra_query_filter:
            query = query.filter(table.extra_query_filter)
        return self.view_filter(query, table)

    def get_lane(self, base_model, kanban_report_lane, lanes, label=None, extra_query_filter=None, multiple=False):

        table = self.chart_js_table(model=base_model)

        report_builder_class = getattr(base_model, kanban_report_lane.report_type.report_builder_class_name, None)

        columns, column_map = get_data_merge_columns(base_model=base_model,
                                                     report_builder_class=report_builder_class,
                                                     html=kanban_report_lane.description)
        if kanban_report_lane.heading_field is not None:
            table.add_columns(kanban_report_lane.heading_field)

        if kanban_report_lane.description is not None:
            table.add_columns(DescriptionColumn(column_name='description',
                                                field='',
                                                html=kanban_report_lane.description,
                                                column_map=column_map))
        table.add_columns(*columns)

        if kanban_report_lane.link_field:
            _, col_type_override, _, _ = get_field_details(base_model=base_model,
                                                           field=kanban_report_lane.link_field)
            if isinstance(col_type_override.field, list):
                field = col_type_override.field[0]
            else:
                field = 'id'
            if field not in columns:
                table.add_columns(f'.{field}')
            table.has_link = True
            table.table_options['row_href'] = row_link(col_type_override.url, field)
        else:
            table.has_link = False


            # table.add_columns(kanban_report_lane.link_field)

        table.datatable_template = 'advanced_report_builder/kanban/middle.html'

        if kanban_report_lane.order_by_field:
            if kanban_report_lane.order_by_ascending:
                table.order_by = [kanban_report_lane.order_by_field]
            else:
                table.order_by = [f'-{kanban_report_lane.order_by_field}']

        table.query_data = kanban_report_lane.query_data
        table.extra_query_filter = extra_query_filter
        table.view_filter = self.view_filter_extra
        lanes.append({'datatable': table,
                      'label': label,
                      'kanban_report_lane': kanban_report_lane,
                      'multiple': multiple})

    @staticmethod
    def get_multiple_date(multiple_type, current_date):
        if multiple_type in (KanbanReportLane.MULTIPLE_TYPE_DAILY, KanbanReportLane.MULTIPLE_TYPE_DAILY_WITHIN):
            return current_date + timedelta(days=1)
        elif multiple_type in (KanbanReportLane.MULTIPLE_TYPE_WEEKLY, KanbanReportLane.MULTIPLE_TYPE_WEEKLY_WITHIN):
            return current_date + timedelta(days=7)
        elif multiple_type in (KanbanReportLane.MULTIPLE_TYPE_MONTHLY, KanbanReportLane.MULTIPLE_TYPE_MONTHLY_WITHIN):
            start_date = date(current_date.year, current_date.month, 1)
            number_of_days = monthrange(current_date.current_date, current_date.month)[1]
            return start_date + timedelta(days=number_of_days)
        assert False

    @staticmethod
    def get_date_format():
        return DATE_FORMAT_TYPES_DJANGO_FORMAT[DATE_FORMAT_TYPE_DD_MM_YY_SLASH]

    @staticmethod
    def get_month_format():
        return DATE_FORMAT_TYPES_DJANGO_FORMAT[DATE_FORMAT_TYPE_DD_MM_YY_SLASH]

    def get_full_label(self, multiple_type, current_date, label):
        if multiple_type in (KanbanReportLane.MULTIPLE_TYPE_DAILY, KanbanReportLane.MULTIPLE_TYPE_DAILY_WITHIN):
            date_string = date.strftime(current_date, self.get_date_format())
            return f'{label} {date_string}'
        elif multiple_type in (KanbanReportLane.MULTIPLE_TYPE_WEEKLY, KanbanReportLane.MULTIPLE_TYPE_WEEKLY_WITHIN):
            date_string = date.strftime(current_date, self.get_date_format())
            week_number = current_date.isocalendar()[1]
            return f'{label} {date_string} (w/c {week_number})'
        elif multiple_type in (KanbanReportLane.MULTIPLE_TYPE_MONTHLY, KanbanReportLane.MULTIPLE_TYPE_MONTHLY_WITHIN):
            date_string = date.strftime(current_date, self.get_date_format())
            return f'{label} {date_string}'
        assert False

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = self.get_title()
        kanban_report_lanes = self.chart_report.kanbanreportlane_set.all()
        lanes = []
        headings = []
        for kanban_report_lane in kanban_report_lanes:
            base_model = kanban_report_lane.get_base_modal()
            if kanban_report_lane.multiple_type == KanbanReportLane.MULTIPLE_TYPE_NA:
                self.get_lane(base_model=base_model,
                              kanban_report_lane=kanban_report_lane,
                              lanes=lanes)
                headings.append({'label': kanban_report_lane.name,
                                 'row_span': 2,
                                 'col_span': 1})
            else:
                variable_date = VariableDate()
                start_date_and_time, _, _ = variable_date.get_variable_dates(kanban_report_lane.multiple_start_period)
                _, end_date_and_time, _ = variable_date.get_variable_dates(kanban_report_lane.multiple_end_period)

                multiple_type = kanban_report_lane.multiple_type
                current_start_date = start_date_and_time

                _, _, _, field_name = get_field_details(base_model=base_model,
                                                        field=kanban_report_lane.multiple_type_date_field)

                end_field_name = None
                if kanban_report_lane.multiple_type_end_date_field:
                    _, _, _, end_field_name = get_field_details(base_model=base_model,
                                                                field=kanban_report_lane.multiple_type_end_date_field)

                sub_lanes = []
                while (current_end_date := self.get_multiple_date(
                        multiple_type=multiple_type,
                        current_date=current_start_date)) <= end_date_and_time:

                    if multiple_type in (KanbanReportLane.MULTIPLE_TYPE_DAILY,
                                         KanbanReportLane.MULTIPLE_TYPE_WEEKLY,
                                         KanbanReportLane.MULTIPLE_TYPE_MONTHLY):
                        query_filter = Q((field_name + "__gte", current_start_date)) &\
                                       (Q((field_name + "__lt", current_end_date)))
                    else:

                        query_filter = Q((end_field_name + "__gte", current_start_date)) &\
                                        (Q((field_name + "__lt", current_end_date)))

                    label = self.get_full_label(multiple_type=multiple_type,
                                                current_date=current_start_date,
                                                label=kanban_report_lane.multiple_type_label)

                    self.get_lane(base_model=base_model,
                                  kanban_report_lane=kanban_report_lane,
                                  lanes=sub_lanes,
                                  label=label,
                                  extra_query_filter=query_filter,
                                  multiple=True)
                    current_start_date = current_end_date

                headings.append({'label': kanban_report_lane.name,
                                 'col_span': len(sub_lanes),
                                 'row_span': 1})

                lanes += sub_lanes

        context['kanban_report'] = self.chart_report
        context['headings'] = headings
        context['lanes'] = lanes
        return context

    def view_filter(self, query, table):
        if not table.query_data:
            return query

        return self.process_query_filters(query=query,
                                          search_filter_data=table.query_data)

    # noinspection PyMethodMayBeStatic
    def pod_dashboard_view_menu(self):
        return []

    def pod_report_menu(self):
        return [MenuItem(f'advanced_report_builder:kanban_modal,pk-{self.chart_report.id}',
                         menu_display='Edit',
                         font_awesome='fas fa-pencil-alt', css_classes=['btn-primary']),
                *self.duplicate_menu(request=self.request, report_id=self.chart_report.id)
                ]

    def pod_dashboard_edit_menu(self):
        return [MenuItem(f'advanced_report_builder:dashboard_report_modal,pk-{self.dashboard_report.id}',
                         menu_display='Edit',
                         font_awesome='fas fa-pencil-alt', css_classes=['btn-primary'])]

    # noinspection PyMethodMayBeStatic
    def queries_menu(self):
        return []


class KanbanModal(ModelFormModal):
    size = 'xl'
    process = PROCESS_EDIT_DELETE
    permission_delete = PERMISSION_OFF
    model = KanbanReport
    widgets = {'report_tags': Select2Multiple}
    ajax_commands = ['datatable', 'button']

    form_fields = ['name',
                   'notes',
                   'report_tags']

    def form_setup(self, form, *_args, **_kwargs):
        org_id = self.object.id if hasattr(self, 'object') else None
        form.fields['notes'].widget.attrs['rows'] = 3
        if org_id is not None:

            menu_items = [MenuItem(f'advanced_report_builder:kanban_lane_duplicate_modal,pk-{DUMMY_ID}',
                                   menu_display='Duplicate',
                                   css_classes='btn btn-sm btn-outline-dark',
                                   font_awesome='fas fa-clone'),
                          MenuItem(f'advanced_report_builder:kanban_lane_modal,pk-{DUMMY_ID}',
                                   menu_display='Edit',
                                   css_classes='btn btn-sm btn-outline-dark',
                                   font_awesome='fas fa-pencil')]

            form.fields['order'] = CharField(
                required=False,
                widget=DataTableReorderWidget(
                    model=KanbanReportLane,
                    order_field='order',
                    fields=['_.index',
                            '.id',
                            'name',
                            MenuColumn(column_name='menu', field='id',
                                       column_defs={'orderable': False, 'className': 'dt-right'},
                                       menu=HtmlMenu(self.request, 'button_group').add_items(*menu_items)),
                            ],
                    attrs={'filter': {'kanban_report__id': self.object.id}})
            )

            modal_button('Custom Close', 'close', 'btn-warning')

            return [*self.form_fields,
                    crispy_modal_link_args('advanced_report_builder:kanban_lane_modal', 'Add Lane',
                                           'kanban_report_id-', self.object.id, div=True,
                                           div_classes='float-right', button_classes='btn btn-primary',
                                           font_awesome='fa fa-plus'),
                    'order']

    def datatable_sort(self, **kwargs):
        current_sort = dict(KanbanReportLane.objects.filter(kanban_report=self.object.id).values_list('id', 'order'))
        for s in kwargs['sort']:
            if current_sort[s[1]] != s[0]:
                o = KanbanReportLane.objects.get(id=s[1])
                o.order = s[0]
                o.save()
        return self.command_response('')

    def post_save(self, created):
        if created:
            self.modal_redirect(self.request.resolver_match.view_name, slug=f'pk-{self.object.id}-new-True')
        else:
            url_name = getattr(settings, 'REPORT_BUILDER_DETAIL_URL_NAME', '')
            if url_name and self.slug.get('new'):
                url = reverse(url_name, kwargs={'slug': self.object.slug})
                self.command_response('redirect', url=url)


class KanbanLaneModal(QueryBuilderModalBase):
    template_name = 'advanced_report_builder/kanban/modal.html'
    size = 'xl'
    process = PROCESS_EDIT_DELETE
    permission_delete = PERMISSION_OFF
    model = KanbanReportLane

    widgets = {'report_tags': Select2Multiple,
               'order_by_ascending': RBToggle}

    form_fields = ['name',
                   'report_type',
                   'heading_field',
                   'order_by_field',
                   'order_by_ascending',
                   'multiple_type',
                   'multiple_type_label',
                   'multiple_type_date_field',
                   'multiple_type_end_date_field',
                   'multiple_start_period',
                   'multiple_end_period',
                   'description',
                   'link_field',
                   'query_data']

    def form_setup(self, form, *_args, **_kwargs):
        form.add_trigger('multiple_type', 'onchange', [
            {'selector': '#div_id_multiple_type_label,#div_id_multiple_type_date_field,'
                         '#div_id_multiple_start_period,#div_id_multiple_end_period',
             'values': {KanbanReportLane.MULTIPLE_TYPE_NA: 'hide'}, 'default': 'show'},
            {'selector': '#div_id_multiple_type_end_date_field',
             'values': {KanbanReportLane.MULTIPLE_TYPE_DAILY_WITHIN: 'show',
                        KanbanReportLane.MULTIPLE_TYPE_WEEKLY_WITHIN: 'show',
                        KanbanReportLane.MULTIPLE_TYPE_MONTHLY_WITHIN: 'show'},
             'default': 'hide'},
        ])

        heading_fields = []
        if 'data' in _kwargs:
            heading_field = _kwargs['data'].get('heading_field')
            order_by_field = _kwargs['data'].get('order_by_field')
            multiple_type_date_field = _kwargs['data'].get('multiple_type_date_field')
            multiple_type_end_date_field = _kwargs['data'].get('multiple_type_end_date_field')
            link_field = _kwargs['data'].get('link_field')
            report_type_id = _kwargs['data'].get('report_type')
            report_type = get_object_or_404(ReportType, id=report_type_id)
        else:
            heading_field = form.instance.heading_field
            order_by_field = form.instance.order_by_field
            report_type = form.instance.report_type
            multiple_type_date_field = form.instance.multiple_type_date_field
            multiple_type_end_date_field = form.instance.multiple_type_end_date_field
            link_field = form.instance.link_field

        if heading_field:
            form.fields['heading_field'].initial = heading_field
            base_model = report_type.content_type.model_class()
            report_builder_fields = getattr(base_model, report_type.report_builder_class_name, None)
            self._get_fields(base_model=base_model,
                             fields=heading_fields,
                             report_builder_class=report_builder_fields,
                             selected_field_id=heading_field,
                             for_select2=True)
        form.fields['heading_field'].widget = Select2(attrs={'ajax': True})
        form.fields['heading_field'].widget.select_data = heading_fields

        self.setup_date_field(form=form,
                              field_name='order_by_field',
                              selected_field_id=order_by_field,
                              report_type=report_type)

        self.setup_date_field(form=form,
                              field_name='multiple_type_date_field',
                              selected_field_id=multiple_type_date_field,
                              report_type=report_type)

        self.setup_date_field(form=form,
                              field_name='multiple_type_end_date_field',
                              selected_field_id=multiple_type_end_date_field,
                              report_type=report_type)
        link_fields = []
        if link_field:
            form.fields['link_field'].initial = link_field
            base_model = report_type.content_type.model_class()
            report_builder_fields = getattr(base_model, report_type.report_builder_class_name, None)
            self._get_column_link_fields(base_model=base_model,
                                         fields=link_fields,
                                         report_builder_class=report_builder_fields,
                                         selected_field_id=link_field)
        form.fields['link_field'].widget = Select2(attrs={'ajax': True})
        form.fields['link_field'].widget.select_data = link_fields

        form.fields['description'].widget = DataMergeWidget()

        range_type_choices = VariableDate.RANGE_TYPE_CHOICES
        form.fields['multiple_start_period'] = ChoiceField(required=False, choices=range_type_choices)
        form.fields['multiple_end_period'] = ChoiceField(required=False, choices=range_type_choices)

        return ('name',
                'report_type',
                'heading_field',
                'order_by_field',
                'order_by_ascending',
                'multiple_type',
                'multiple_type_label',
                'multiple_type_date_field',
                'multiple_type_end_date_field',
                'multiple_start_period',
                'multiple_end_period',
                'description',
                'link_field',
                FieldEx('query_data',
                        template='advanced_report_builder/query_builder.html'),
                )

    def setup_date_field(self, form, field_name, selected_field_id, report_type):
        _fields = []
        if selected_field_id:
            form.fields[field_name].initial = selected_field_id
            base_model = report_type.content_type.model_class()
            report_builder_fields = getattr(base_model, report_type.report_builder_class_name, None)
            self._get_date_fields(base_model=base_model,
                                  fields=_fields,
                                  report_builder_class=report_builder_fields,
                                  selected_field_id=selected_field_id)
        form.fields[field_name].widget = Select2(attrs={'ajax': True})
        form.fields[field_name].widget.select_data = _fields

    def select2_link_field(self, **kwargs):
        fields = []
        if kwargs['report_type'] != '':
            report_builder_fields, base_model = self.get_report_builder_class(report_type_id=kwargs['report_type'])
            fields = []
            self._get_column_link_fields(base_model=base_model,
                                         fields=fields,
                                         report_builder_class=report_builder_fields,
                                         search_string=kwargs.get('search'))

        return JsonResponse({'results': fields})

    def select2_heading_field(self, **kwargs):
        fields = []
        if kwargs['report_type'] != '':
            report_builder_fields, base_model = self.get_report_builder_class(report_type_id=kwargs['report_type'])
            fields = []
            self._get_fields(base_model=base_model,
                             fields=fields,
                             report_builder_class=report_builder_fields,
                             for_select2=True,
                             search_string=kwargs.get('search'))

        return JsonResponse({'results': fields})

    def select2_order_by_field(self, **kwargs):
        return self.get_date_fields_for_select2(report_type=kwargs['report_type'],
                                                search_string=kwargs.get('search'))

    def select2_multiple_type_date_field(self, **kwargs):
        return self.get_date_fields_for_select2(report_type=kwargs['report_type'],
                                                search_string=kwargs.get('search'))

    def select2_multiple_type_end_date_field(self, **kwargs):
        return self.get_date_fields_for_select2(report_type=kwargs['report_type'],
                                                search_string=kwargs.get('search'))

    def get_date_fields_for_select2(self, report_type, search_string):
        fields = []
        if report_type != '':
            report_builder_fields, base_model = self.get_report_builder_class(report_type_id=report_type)
            fields = []
            self._get_date_fields(base_model=base_model,
                                  fields=fields,
                                  report_builder_class=report_builder_fields,
                                  search_string=search_string)
        return JsonResponse({'results': fields})

    def ajax_get_data_merge_menu(self, **kwargs):
        field_auto_id = kwargs['field_auto_id']
        menus = []
        if kwargs['report_type'] != '':
            report_builder_class, base_model = self.get_report_builder_class(report_type_id=kwargs['report_type'])

            get_menu_fields(base_model=base_model,
                            report_builder_class=report_builder_class,
                            menus=menus)

            menus = [{'code': 'data_merge',
                      'text': 'Data Merge',
                      'menu': menus}]

        return self.command_response(f'build_data_merge_menu_{field_auto_id}',
                                     data=json.dumps(menus))

    def form_valid(self, form):
        form.save()
        return self.command_response('reload')


class KanbanLaneDuplicateModal(Modal):

    def modal_content(self):
        return 'Are you sure you want to duplicate this lane?'

    def get_modal_buttons(self):
        return [modal_button_method('Confirm', 'duplicate'), modal_button('Cancel', 'close', 'btn-secondary')]

    def button_duplicate(self, **_kwargs):
        kanban_report_lane = get_object_or_404(KanbanReportLane, id=self.slug['pk'])
        kanban_report_lane.pk = None
        kanban_report_lane.name = f'Copy of {kanban_report_lane.name}'
        kanban_report_lane.order = None
        kanban_report_lane.save()
        return self.command_response('reload')
